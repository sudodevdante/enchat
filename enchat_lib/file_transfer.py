import os
import hashlib
import uuid

from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from . import state, constants, notifications
from .state import outbox_queue

def ensure_file_dir():
    """Ensure secure temporary directory exists"""
    os.makedirs(constants.FILE_TEMP_DIR, mode=0o700, exist_ok=True)

def ensure_downloads_dir():
    """Ensure downloads directory exists in project folder"""
    os.makedirs(constants.DOWNLOADS_DIR, exist_ok=True)

def sanitize_filename(filename, fallback_id="unknown"):
    """
    Sanitize filename to prevent directory traversal and other security issues.
    Returns a safe filename suitable for use in downloads directory.
    """
    if not filename:
        return f"file_{fallback_id}"
    
    safe_name = os.path.basename(filename)
    
    if not safe_name or safe_name in ('.', '..') or safe_name.startswith('.'):
        return f"file_{fallback_id}"
    
    import re
    safe_name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', safe_name)
    
    if len(safe_name) > 255:
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:255-len(ext)] + ext
    
    return safe_name if safe_name else f"file_{fallback_id}"

def split_file_to_chunks(filepath, f_cipher):
    """Split file into encrypted chunks for transfer"""
    if not os.path.exists(filepath):
        return None, "File not found"
    
    file_size = os.path.getsize(filepath)
    if file_size > constants.MAX_FILE_SIZE:
        return None, f"File too large (max {constants.MAX_FILE_SIZE // (1024*1024)}MB)"
    
    file_id = str(uuid.uuid4())[:8]
    filename = os.path.basename(filepath)
    file_hash = hashlib.sha256()
    chunks = []
    
    try:
        with open(filepath, 'rb') as f:
            chunk_num = 0
            while True:
                chunk_data = f.read(constants.CHUNK_SIZE)
                if not chunk_data:
                    break
                
                file_hash.update(chunk_data)
                encrypted_chunk = f_cipher.encrypt(chunk_data).decode()
                chunks.append({
                    'file_id': file_id,
                    'chunk_num': chunk_num,
                    'data': encrypted_chunk
                })
                chunk_num += 1
        
        metadata = {
            'file_id': file_id,
            'filename': filename,
            'size': file_size,
            'total_chunks': len(chunks),
            'hash': file_hash.hexdigest()
        }
        
        return metadata, chunks
    except Exception as e:
        return None, f"Error reading file: {e}"

def handle_file_metadata(metadata, sender, buf):
    """Handle incoming file metadata, resilient to out-of-order messages."""
    file_id = metadata['file_id']
    
    # If this is the first we're hearing of this file, create its state.
    if file_id not in state.available_files:
        state.file_chunks[file_id] = {}
        state.available_files[file_id] = {
            'sender': sender,
            'chunks_received': 0,
            'complete': False
        }
        
    # Update the state with the authoritative metadata.
    state.available_files[file_id]['metadata'] = metadata
    state.available_files[file_id]['total_chunks'] = metadata['total_chunks']

    # Display the initial notification panel.
    size_mb = metadata['size'] / (1024 * 1024)
    sender_escaped = escape(sender)
    filename_escaped = escape(metadata['filename'])
    
    panel_text = f"• [bold]From:[/bold] [cyan]{sender_escaped}[/]\n"
    panel_text += f"• [bold]File:[/bold] [yellow]{filename_escaped}[/]\n"
    panel_text += f"• [bold]Size:[/bold] [yellow]{size_mb:.1f}MB[/] ({metadata['total_chunks']} chunks)\n\n"
    panel_text += f"• [bold]File ID:[/bold] [magenta]{file_id}[/]\n\n"
    panel_text += f"[dim]Use '/download {file_id}' once transfer is complete.[/dim]"
    
    panel = Panel(
        Text.from_markup(panel_text),
        title="[bold blue]📎 File Transfer Incoming[/]",
        border_style="blue",
        padding=(1, 2)
    )
    buf.append(("System", panel, False))
    notifications.notify(f"{sender} shared file: {metadata['filename']}")
    
    # After receiving metadata, check if previously received chunks complete the file.
    _check_file_completion(file_id, buf)

def handle_file_chunk(chunk_data, sender, buf):
    """Handle incoming file chunk, resilient to out-of-order messages."""
    file_id = chunk_data['file_id']
    chunk_num = chunk_data['chunk_num']

    # If this is the first we're hearing of this file, create a placeholder.
    if file_id not in state.available_files:
        state.file_chunks[file_id] = {}
        state.available_files[file_id] = {
            'metadata': None,
            'sender': sender,
            'chunks_received': 0,
            'total_chunks': -1, # Sentinel for unknown total
            'complete': False
        }

    # Don't process chunks for files that are already marked as complete.
    if state.available_files[file_id]['complete']:
        return

    # Store the chunk and update the received count.
    if chunk_num not in state.file_chunks[file_id]:
        state.file_chunks[file_id][chunk_num] = chunk_data
        state.available_files[file_id]['chunks_received'] = len(state.file_chunks[file_id])

    # Check for completion. This can only happen if metadata has arrived.
    _check_file_completion(file_id, buf)

def _check_file_completion(file_id, buf):
    """Check if a file has all its chunks and notify if complete."""
    file_info = state.available_files.get(file_id)
    
    # Cannot be complete if we don't have metadata or it's already marked complete.
    if not file_info or not file_info.get('metadata') or file_info.get('complete'):
        return

    received = file_info['chunks_received']
    total = file_info['total_chunks']
    
    if total > 0 and received == total:
        file_info['complete'] = True
        filename_escaped = escape(file_info['metadata']['filename'])
        
        panel_text = f"• [bold]File:[/bold] [yellow]{filename_escaped}[/]\n"
        panel_text += "• [bold]Status:[/bold] [green]100% Complete[/]\n\n"
        panel_text += f"Ready to be saved with: [bold cyan]/download {file_id}[/]"

        panel = Panel(
            Text.from_markup(panel_text),
            title="[bold green]✅ File Ready for Download[/]",
            border_style="green",
            padding=(1, 2)
        )
        buf.append(("System", panel, False))
        notifications.notify(f"File ready to download: {file_info['metadata']['filename']}")

def assemble_file_from_chunks(file_id, f_cipher):
    """Assemble file from chunks and save to temp directory"""
    if file_id not in state.available_files or not state.available_files[file_id]['complete']:
        return None, "File not available or incomplete"
    
    ensure_file_dir()
    metadata = state.available_files[file_id]['metadata']
    chunks_dict = state.file_chunks[file_id]
    
    try:
        temp_path = os.path.join(constants.FILE_TEMP_DIR, f"{file_id}_{metadata['filename']}")
        file_hash = hashlib.sha256()
        
        if metadata['total_chunks'] == 0:
            with open(temp_path, 'wb') as f:
                pass
            file_hash.update(b'')
        else:
            sorted_chunks = [chunks_dict[i] for i in sorted(chunks_dict.keys())]
            
            with open(temp_path, 'wb') as f:
                for chunk in sorted_chunks:
                    decrypted_data = f_cipher.decrypt(chunk['data'].encode())
                    file_hash.update(decrypted_data)
                    f.write(decrypted_data)
        
        if file_hash.hexdigest() != metadata['hash']:
            os.remove(temp_path)
            return None, "File integrity check failed"
        
        return temp_path, None
    except Exception as e:
        return None, f"Error assembling file: {e}"

def enqueue_file_transfer(room, nick, metadata, chunks, server, f):
    """Enqueue the entire file transfer operation."""
    payload = {
        "metadata": metadata,
        "chunks": chunks
    }
    outbox_queue.put(("FILE_TRANSFER", room, nick, payload, server, f))
