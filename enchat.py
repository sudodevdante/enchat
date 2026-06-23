#!/usr/bin/env python3
"""enchat – encrypted terminal chat
Route B • 2025-06-15
"""
import argparse
import base64
import os
import signal
import sys
import threading
import time
from getpass import getpass
from typing import List, Tuple

from cryptography.fernet import Fernet
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

# Local modules from enchat_lib
from enchat_lib import (
    config, constants, crypto, network, secure_wipe, ui, public_rooms, state, link_sharing
)
from enchat_lib.constants import VERSION, KEYRING_AVAILABLE

console = Console()

# --- Globals ---
SHUTDOWN_EVENT = threading.Event()

def _render_header(title: str):
    """Renders a standardized header panel."""
    console.clear()
    header_text = Text("enchat", style="bold cyan", justify="center")
    panel = Panel(
        header_text,
        title=f"v{VERSION}",
        subtitle=f"[bold blue]{title}[/]",
        border_style="blue"
    )
    console.print(panel)
    console.print()

def first_run(args):
    """Guides the user through the first-time setup with an enhanced UI."""
    _render_header("First-Time Setup")
    
    console.print(Panel(
        Text.from_markup(
            "Welcome to [bold cyan]enchat[/]! Let's get you set up."
        ),
        title="Welcome",
        border_style="green",
        padding=(1, 2)
    ))
    
    action = Prompt.ask(
        Text.from_markup(
            "\nWhat would you like to do?\n\n"
            "   [bold]1)[/] [cyan]Private Room[/] (Create/Join)\n"
            "   [bold]2)[/] [yellow]Public Room[/] (Join)"
        ),
        choices=["1", "2"],
        show_choices=False,
        default="1"
    )

    if action == "2":
        # Pass the original args to ensure the --tor flag is propagated
        join_public_room(args)
        return None, None, None, None

    console.print(Panel(
        Text.from_markup(
            "A [bold]Room[/] is a shared chat space.\n"
            "A [bold]Passphrase[/] is the key to that room. [bold red]Never lose it![/]"
        ),
        title="Private Room Setup",
        border_style="blue",
        padding=(1, 2)
    ))
    
    room = Prompt.ask("🏠 Room Name")
    nick = Prompt.ask("👤 Nickname")
    secret = getpass("🔑 Passphrase (will be hidden)")
    
    server_url = getattr(args, 'server', None)
    if server_url:
        server = server_url.rstrip('/')
        console.print(f"🌍 Using custom server: [bold cyan]{server}[/]")
    else:
        console.print("📡 Please choose a server:")
        choice = Prompt.ask(
            Text.from_markup(
                "   [bold]1)[/] [green]Enchat Server[/] (Recommended, private)\n"
                "   [bold]2)[/] [yellow]Public ntfy.sh[/] (Functional, less private)\n"
                "   [bold]3)[/] [cyan]Custom Server[/]"
            ),
            choices=["1", "2", "3"],
            default="1"
        )
        server = constants.ENCHAT_NTFY if choice == "1" else constants.DEFAULT_NTFY if choice == "2" else Prompt.ask("Enter Custom Server URL").rstrip('/')

    if Prompt.ask("\n💾 Save these settings for next time?", choices=["y", "n"], default="y") == "y":
        if KEYRING_AVAILABLE and Prompt.ask("🔐 Save passphrase securely in system keychain?", choices=["y", "n"], default="y") == "y":
            config.save_passphrase_keychain(room, secret)
        config.save_conf(room, nick, "", server)
        console.print("[green]Settings saved.[/]")
        
    return room, nick, secret, server

def start_chat(room: str, nick: str, secret: str, server: str, buf: List[Tuple[str, str, bool]], is_public: bool = False, is_tor: bool = False):
    """Initializes and runs the chat UI."""
    if not secret:
        # Prompt for passphrase if not provided (e.g. on subsequent runs without keychain)
        secret = getpass(f"🔑 Passphrase for room '{room}': ")

    f = Fernet(crypto.gen_key(secret, room))
    
    # Start the outbox worker thread
    out_stop = threading.Event()
    outbox_thread = threading.Thread(target=network.outbox_worker, args=(out_stop,), daemon=True)
    outbox_thread.start()

    # Pass the main shutdown event and room secret to the UI
    chat_ui = ui.ChatUI(room, nick, server, f, buf, secret, is_public, is_tor, SHUTDOWN_EVENT)
    
    def quit_handler(*_):
        """Signal handler for graceful shutdown."""
        # This will trigger the exit condition in the main loop
        SHUTDOWN_EVENT.set()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, quit_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, quit_handler)  # Termination signal
    if hasattr(signal, 'SIGHUP'):                # Unix only (not available on Windows)
        signal.signal(signal.SIGHUP, quit_handler)
    
    try:
        chat_ui.run()
    finally:
        # This block runs on any exit path: /exit, Ctrl+C, etc.
        console.print("\n[yellow]Disconnecting...[/]")
        
        # 1. Enqueue the 'left' message
        network.enqueue_sys(room, nick, "left", server, f)
        
        # 2. Wait for the outbox to be empty, ensuring the message is sent
        state.outbox_queue.join()
        
        # 3. Stop all background threads
        out_stop.set()
        
        console.print("[bold green]✓ Session closed.[/]")

def join_room(args):
    """Handler for the 'join' command with an enhanced UI."""
    _render_header("Join Room")
    room_name = args.room or Prompt.ask("🏠 Room Name to join")
    display_name = args.name or Prompt.ask("👤 Your Nickname")
    secret = getpass("🔑 Room Passphrase (will be hidden)")
    server = args.server or constants.DEFAULT_NTFY
    
    if Prompt.ask("\n💾 Save these room settings for next time?", choices=["y", "n"], default="n") == 'y':
        if KEYRING_AVAILABLE and Prompt.ask("🔐 Save passphrase securely in system keychain?", choices=["y","n"], default="y")=="y":
            config.save_passphrase_keychain(room_name, secret)
        config.save_conf(room_name, display_name, "", server)
        console.print("[green]Settings saved.[/]")

    console.print(f"\n[green]Joining room '{room_name}' as '{display_name}'...[/]")
    start_chat(room_name, display_name, secret, server, [], is_tor=args.tor)


def create_room(args):
    """Handler for the 'create' command with an enhanced UI."""
    _render_header("Create New Room")
    room_name = args.room or Prompt.ask("🏠 New Room Name")
    room_key = base64.urlsafe_b64encode(os.urandom(32)).decode()

    key_panel = Panel(
        Text(room_key, justify="center", style="bold yellow"),
        title="🔑 Your New Room Key",
        border_style="red",
        subtitle="[dim]Share this with other participants[/]"
    )
    console.print(key_panel)
    console.print(Text.from_markup("[bold red]Warning:[/b red] You cannot recover this key. Store it securely!"))
    
    if Prompt.ask("\n🤝 Join this room now?", choices=["y", "n"], default="y") == 'y':
        display_name = Prompt.ask("👤 Your Nickname")
        server = args.server or constants.DEFAULT_NTFY
        
        if Prompt.ask("💾 Save these room settings for next time?", choices=["y", "n"], default="n") == 'y':
            if KEYRING_AVAILABLE and Prompt.ask("🔐 Save new room key in system keychain?", choices=["y","n"], default="y") == 'y':
                config.save_passphrase_keychain(room_name, room_key)
            config.save_conf(room_name, display_name, "", server)
            console.print("[green]Settings saved.[/]")

        start_chat(room_name, display_name, room_key, server, [], is_tor=args.tor)

def join_public_room(args):
    """Handler for the 'public' command."""
    _render_header("Public Rooms")
    
    room_alias = getattr(args, 'room_name', None)
    available_rooms = public_rooms.PUBLIC_ROOMS.keys()
    
    if not room_alias:
        room_alias = Prompt.ask("Which public room would you like to join?", choices=list(available_rooms))

    if room_alias not in public_rooms.PUBLIC_ROOMS:
        console.print(f"[bold red]Error: Public room '{room_alias}' not found.[/]")
        console.print(f"Available public rooms are: [cyan]{', '.join(available_rooms)}[/]")
        return

    room_name, secret = public_rooms.PUBLIC_ROOMS[room_alias]
    server = constants.ENCHAT_NTFY # Public rooms are on the default Enchat server
    
    console.print(Text.from_markup(f"Joining public room: [bold cyan]{room_alias}[/].\n"), justify="center")
    console.print(Panel(
        Text.from_markup(
            "[bold yellow]Welcome![/] Public rooms are encrypted, but the passphrase is public knowledge.\n"
            "Do not share any private information here."
        ),
        title="⚠️ Public Room Notice",
        border_style="yellow",
        padding=(1,2)
    ))

    display_name = Prompt.ask("👤 Your Nickname")
    
    console.print(f"\n[green]Connecting to '{room_alias}' as '{display_name}'...[/]")
    start_chat(room_name, display_name, secret, server, [], is_public=True, is_tor=args.tor)

def join_from_link(args):
    """Handler for joining a room from a one-time-use link."""
    _render_header("Join via Secure Link")
    console.print(f"🔗 Attempting to use link: {args.link_url}")

    parsed = link_sharing.parse_share_url(args.link_url)
    if not parsed:
        console.print("[bold red]Error: The provided link is malformed.[/]")
        return
        
    session_id, key = parsed
    
    payload = link_sharing.get_remote_payload(session_id)
    if not payload:
        console.print("[bold red]Error: Could not retrieve room details.[/]")
        console.print("[dim]This link may have expired or has already been used.[/dim]")
        return
        
    try:
        room_name, server, secret = link_sharing.decrypt_credentials(payload, key)
    except Exception:
        console.print("[bold red]Error: Failed to decrypt room details. The link may be corrupt.[/]")
        return
        
    console.print(f"[bold green]✓ Successfully retrieved room details for '[cyan]{room_name}[/]'[/]")
    console.print(f"🌍 Connecting via server: [bold cyan]{server}[/]")
    
    display_name = Prompt.ask("👤 Your Nickname")
    
    start_chat(room_name, display_name, secret, server, [], is_tor=args.tor)

def main():
    """Main entry point: parses arguments and starts the correct action."""
    parser = argparse.ArgumentParser(
        description="enchat – encrypted terminal chat.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('--server', help='Custom ntfy server URL to override saved/default.')
    parser.add_argument('--tor', action='store_true', help='Route traffic through the Tor network (requires Tor to be running).')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Default command (run with existing config)
    run_parser = subparsers.add_parser('run', help='Run Enchat with saved settings (default action)')
    
    # Join command
    join_parser = subparsers.add_parser('join', help='Join a new or existing private room.')
    join_parser.add_argument('room', help='Room name to join.')
    join_parser.add_argument('--name', '-n', help='Your display name.')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new private chat room and key.')
    create_parser.add_argument('room', nargs='?', default=None, help='Name of the room to create (optional).')

    # Public command
    public_parser = subparsers.add_parser('public', help='Join a public, less-secure chat room.')
    public_parser.add_argument(
        'room_name', 
        nargs='?',
        default=None,
        choices=list(public_rooms.PUBLIC_ROOMS.keys()) + [None],
        help='Name of the public room to join. If omitted, a list will be shown.'
    )

    # Join from link command
    join_link_parser = subparsers.add_parser('join-link', help='Join a room using a secure, one-time link.')
    join_link_parser.add_argument('link_url', help='The full enchat share link.')

    # Maintenance commands
    reset_parser = subparsers.add_parser('reset', help='Clear saved room settings and keys.')
    kill_parser = subparsers.add_parser('kill', help='Securely wipe ALL Enchat data.')
    version_parser = subparsers.add_parser('version', help='Show version info.')

    # If no command is given, default to 'run'
    args = parser.parse_args(sys.argv[1:] if sys.argv[1:] else ['run'])
    
    if args.command == 'version':
        console.print(f"[cyan]Enchat v{VERSION}[/]")
        return
        
    if args.command == 'kill':
        console.print("[bold red]🔥 ENCHAT DATA WIPE - COMPLETE REMOVAL[/]")
        if Prompt.ask("Are you absolutely sure?", choices=["y", "n"], default="n") == 'y':
            secure_wipe.secure_wipe()
        else:
            console.print("[green]Cancelled.[/]")
        return
            
    if args.command == 'reset':
        if Prompt.ask("[bold red]Are you sure you want to clear all settings?", choices=["y", "n"], default="n") == 'y':
            secure_wipe.reset_enchat()
        else:
            console.print("[green]Cancelled.[/]")
        return
        
    if args.command == 'join':
        join_room(args)
        return
        
    if args.command == 'create':
        create_room(args)
        return

    if args.command == 'public':
        join_public_room(args)
        return
        
    if args.command == 'join-link':
        join_from_link(args)
        return

    # Default action: run with config or do first-time setup
    if args.tor:
        network.configure_tor()

    room, nick, secret, server_conf = config.load_conf()
    server = args.server or server_conf
    
    if not all((room, nick, server)) or args.command != 'run':
        # If 'run' is specified but no config, it's a first run.
        # Or if any other command was called that needs setup.
        room, nick, secret, server = first_run(args)

    if room and nick and server:
        start_chat(room, nick, secret, server, [], is_tor=args.tor)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Exited gracefully.[/]")
        sys.exit(0)
