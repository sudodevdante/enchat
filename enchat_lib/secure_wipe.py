import os
import sys
import subprocess
import gc
import secrets
from typing import Tuple, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt

from .config import wipe_keychain_entries

console = Console()

def secure_delete_file(path: str, passes: int = 3) -> Tuple[bool, Optional[str]]:
    """
    Securely delete a file using multiple overwrite passes.
    This version combines the logic from the two original functions.
    """
    if not os.path.exists(path):
        return True, None

    try:
        if os.path.islink(path):
            os.remove(path)
            return True, None

        size = os.path.getsize(path)
        
        # Platform-specific optimizations
        if sys.platform == "darwin":
            # macOS 'rm -P' is a good option, but requires one less pass than our default
            # For consistency, we use our own implementation.
            pass
        elif sys.platform == "linux" and os.path.exists("/usr/bin/shred"):
            result = subprocess.run(['shred', '-u', '-n', str(passes), path], capture_output=True)
            if result.returncode == 0:
                return True, None
        elif sys.platform == "win32":
            # cipher /w is for directories, not single files. Overwriting is more reliable.
            pass

        # Cross-platform multi-pass overwrite
        with open(path, 'wb') as f:
            for _ in range(passes):
                f.write(secrets.token_bytes(size))
                f.flush()
                os.fsync(f.fileno())
        
        os.remove(path)
        return True, None
    except Exception as e:
        # Fallback to normal deletion
        try:
            os.remove(path)
            return True, f"Secure delete failed, used normal delete: {e}"
        except Exception as final_e:
            return False, f"All deletion attempts failed: {final_e}"


def secure_delete_directory(dirpath: str):
    if not os.path.exists(dirpath):
        return
    for root, dirs, files in os.walk(dirpath, topdown=False):
        for name in files:
            secure_delete_file(os.path.join(root, name))
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass # Already deleted or access error
    try:
        os.rmdir(dirpath)
    except OSError:
        pass


def clear_shell_history():
    """Clear Enchat-related entries from shell history."""
    shell = os.environ.get('SHELL', '')
    history_file = None
    if 'zsh' in shell:
        history_file = os.path.expanduser('~/.zsh_history')
    elif 'bash' in shell:
        history_file = os.path.expanduser('~/.bash_history')
    
    if history_file and os.path.exists(history_file):
        try:
            with open(history_file, 'r', errors='ignore') as f:
                lines = f.readlines()
            
            original_len = len(lines)
            lines = [l for l in lines if 'enchat' not in l.lower()]

            if len(lines) < original_len:
                with open(history_file, 'w', errors='ignore') as f:
                    f.writelines(lines)
        except Exception:
            pass # Ignore errors, not critical


def clear_clipboard():
    """Clear system clipboard."""
    try:
        if sys.platform == "darwin":
            subprocess.run(['pbcopy'], input=b'', capture_output=True)
        elif sys.platform == "linux":
            # Try both xsel and xclip for broader compatibility
            if subprocess.run(['which', 'xsel'], capture_output=True).returncode == 0:
                subprocess.run(['xsel', '-cb'], capture_output=True)
            elif subprocess.run(['which', 'xclip'], capture_output=True).returncode == 0:
                 subprocess.run(['xclip', '-selection', 'clipboard', '-in', '/dev/null'], capture_output=True)
        elif sys.platform == "win32":
            subprocess.run(['cmd', '/c', 'echo off | clip'], capture_output=True)
    except Exception:
        pass # Not critical if fails


def secure_memory_wipe(obj: object):
    # This is very hard to achieve in Python. GC is the main tool.
    # The original implementation was complex and platform-specific.
    # A simplified, more portable approach is to rely on GC.
    del obj
    gc.collect()


def secure_wipe():
    """Securely wipe all Enchat data."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        
        overall_task = progress.add_task("[cyan]Wiping Enchat data...", total=100)
        
        # 1. Clear sensitive memory objects (placebo, but harmless)
        progress.update(overall_task, advance=10, description="[cyan]Running garbage collector...")
        gc.collect()
        progress.update(overall_task, advance=10)
        
        # 2. Wipe configuration file
        progress.update(overall_task, description="[cyan]Wiping configuration file...")
        config_path = os.path.expanduser("~/.enchat.conf")
        if os.path.exists(config_path):
            success, error = secure_delete_file(config_path)
            if not success:
                progress.console.print(f"[yellow]⚠️ Warning: Could not fully wipe config: {error}[/]")
        progress.update(overall_task, advance=20)

        # 3. Wipe downloaded files
        progress.update(overall_task, description="[cyan]Wiping downloaded files...")
        downloads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads")
        if os.path.exists(downloads_dir):
            secure_delete_directory(downloads_dir)
        progress.update(overall_task, advance=20)
        
        # 4. Clear keychain entries
        progress.update(overall_task, description="[cyan]Clearing keychain entries...")
        _, keychain_warnings = wipe_keychain_entries()
        if keychain_warnings:
            for warning in keychain_warnings:
                progress.console.print(f"[yellow]⚠️ {warning}[/]")
        progress.update(overall_task, advance=20)
        
        # 5. Clear system artifacts
        progress.update(overall_task, description="[cyan]Clearing system artifacts...")
        clear_clipboard()
        clear_shell_history()
        progress.update(overall_task, advance=10)
        
        # 6. Final cleanup
        progress.update(overall_task, description="[cyan]Performing final cleanup...")
        gc.collect()
        progress.update(overall_task, advance=10)
        
        progress.update(overall_task, description="[bold green]✅ Wipe complete!")
            
    console.print("\n[bold green]🔒 Enchat data has been securely wiped![/]")
    console.print("[dim]Note: Some traces may remain in system memory or filesystem journals.[/]")
    console.print("[dim]For maximum security, consider rebooting your system.[/]")


def reset_enchat():
    """Reset Enchat configuration and keys."""
    console.print("\n[yellow]🔄 ENCHAT RESET - CLEAR CONFIGURATION[/]")
    if Prompt.ask("Are you sure you want to reset Enchat configuration?", choices=["y", "n"], default="n") != 'y':
        console.print("[green]Cancelled - configuration preserved[/]")
        return
    
    console.print("\nClearing configuration...\n")
    
    # 1. Clear config file
    config_path = os.path.expanduser("~/.enchat.conf")
    if os.path.exists(config_path):
        try:
            os.remove(config_path)
            console.print("[green]✅ Configuration file removed.[/]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not delete config file: {e}[/]")
    
    # 2. Clear keychain entries
    success, warnings = wipe_keychain_entries()
    if success:
        console.print("[green]✅ Keychain entries cleared.[/]")
    if warnings:
        for warning in warnings:
            console.print(f"[yellow]⚠️ {warning}[/]")
    
    console.print("\n[bold green]🔄 Reset complete![/]")
