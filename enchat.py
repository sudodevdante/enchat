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
from typing import List, Optional, Tuple

from cryptography.fernet import Fernet
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

# Local modules from enchat_lib
from enchat_lib import (
    config, constants, crypto, network, secure_wipe, ui, public_rooms, state, link_sharing,
    onboarding,
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

def first_run(args, saved_config=None):
    """Run the Textual home and onboarding flow."""
    saved_config = saved_config or (None, None, None, None)
    saved_room, saved_nick, saved_secret, saved_server = saved_config
    result = onboarding.run_onboarding(
        saved_room or "",
        saved_nick or "",
        args.server or constants.ENCHAT_NTFY,
    )
    if result is None:
        return None, None, None, None

    if result.action == "continue":
        return saved_room, saved_nick, saved_secret, args.server or saved_server

    if result.action == "public":
        public_room = public_rooms.PublicRoom(
            room_id=result.public_room_id,
            name=result.public_room,
            topic=result.room,
            secret=result.secret,
        )
        start_chat(
            public_room.topic,
            result.nick,
            public_room.secret,
            args.server or constants.ENCHAT_NTFY,
            [],
            is_public=True,
            is_tor=args.tor,
            room_label=public_room.name,
            public_room=public_room,
        )
        return None, None, None, None

    if result.action == "invite":
        parsed = link_sharing.parse_share_url(result.link)
        if not parsed:
            console.print("[bold red]Invalid invite link.[/]")
            return None, None, None, None
        session_id, key = parsed
        payload = link_sharing.get_remote_payload(session_id)
        if not payload:
            console.print("[bold red]Invite expired, unavailable, or already used.[/]")
            return None, None, None, None
        try:
            room, server, secret = link_sharing.decrypt_credentials(payload, key)
        except Exception:
            console.print("[bold red]Could not decrypt the invitation.[/]")
            return None, None, None, None
        nick = result.nick
    elif result.action == "create":
        room, nick, server = result.room, result.nick, result.server
        secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
        console.print(
            Panel(
                Text(secret, justify="center", style="bold yellow"),
                title="Your room key",
                subtitle="Share this only with people you trust",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    else:
        room, nick, secret, server = (
            result.room,
            result.nick,
            result.secret,
            result.server,
        )

    server = args.server or server
    if result.remember:
        if KEYRING_AVAILABLE and result.save_secret:
            config.save_passphrase_keychain(room, secret)
        config.save_conf(room, nick, "", server)
        console.print("[green]Room settings saved.[/]")

    return room, nick, secret, server

def start_chat(
    room: str,
    nick: str,
    secret: str,
    server: str,
    buf: List[Tuple[str, str, bool]],
    is_public: bool = False,
    is_tor: bool = False,
    room_label: Optional[str] = None,
    public_room: Optional[public_rooms.PublicRoom] = None,
):
    """Initializes and runs the chat UI."""
    if not secret:
        # Prompt for passphrase if not provided (e.g. on subsequent runs without keychain)
        secret = getpass(f"🔑 Passphrase for room '{room}': ")

    SHUTDOWN_EVENT.clear()
    resolved_server = network.resolve_server(server)
    if resolved_server != server.rstrip('/'):
        console.print(
            f"[yellow]Configured relay is unavailable; using {resolved_server} instead.[/]"
        )
    server = resolved_server
    state.relay_status = "connecting"
    state.relay_error = ""

    f = Fernet(crypto.gen_key(secret, room))
    
    # Start the outbox worker thread
    out_stop = threading.Event()
    outbox_thread = threading.Thread(target=network.outbox_worker, args=(out_stop,), daemon=True)
    outbox_thread.start()

    lease_stop = threading.Event()
    if public_room is not None:
        threading.Thread(
            target=public_rooms.maintain_lease,
            args=(public_room, server, lease_stop),
            daemon=True,
        ).start()

    # Pass the main shutdown event and room secret to the UI
    chat_ui = ui.ChatUI(
        room,
        nick,
        server,
        f,
        buf,
        secret,
        is_public,
        is_tor,
        SHUTDOWN_EVENT,
        room_label=room_label,
    )
    
    def quit_handler(*_):
        """Signal handler for graceful shutdown."""
        # This will trigger the exit condition in the main loop
        SHUTDOWN_EVENT.set()

    # Register signal handlers for Ctrl+C and terminal close
    signal.signal(signal.SIGINT, quit_handler)
    signal.signal(signal.SIGTERM, quit_handler)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, quit_handler)
    
    try:
        chat_ui.run()
    finally:
        # This block runs on any exit path: /exit, Ctrl+C, etc.
        console.print("\n[yellow]Disconnecting...[/]")
        
        # 1. Enqueue the 'left' message
        network.enqueue_sys(room, nick, "left", server, f)
        
        # 2. Give the final presence event a brief chance to leave without
        # making shutdown hang when the relay is unreachable.
        network.wait_for_outbox(state.outbox_queue, timeout=3.0)
        
        # 3. Stop all background threads
        out_stop.set()
        lease_stop.set()
        
        console.print("[bold green]✓ Session closed.[/]")

def join_room(args):
    """Handler for the 'join' command with an enhanced UI."""
    if args.room and link_sharing.parse_share_url(args.room):
        args.link_url = args.room
        join_from_link(args)
        return

    _render_header("Join Room")
    room_name = args.room or Prompt.ask("🏠 Room Name to join")
    display_name = args.name or Prompt.ask("👤 Your Nickname")
    secret = getpass("🔑 Room Passphrase (will be hidden)")
    server = args.server or constants.ENCHAT_NTFY
    
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
        server = args.server or constants.ENCHAT_NTFY
        
        if Prompt.ask("💾 Save these room settings for next time?", choices=["y", "n"], default="n") == 'y':
            if KEYRING_AVAILABLE and Prompt.ask("🔐 Save new room key in system keychain?", choices=["y","n"], default="y") == 'y':
                config.save_passphrase_keychain(room_name, room_key)
            config.save_conf(room_name, display_name, "", server)
            console.print("[green]Settings saved.[/]")

        start_chat(room_name, display_name, room_key, server, [], is_tor=args.tor)

def join_public_room(args):
    """Handler for the 'public' command."""
    _render_header("Public Rooms")

    server = args.server or constants.ENCHAT_NTFY
    try:
        rooms = public_rooms.list_active_rooms(server)
    except public_rooms.DirectoryUnavailable:
        console.print("[red]The public-room directory is currently unreachable.[/]")
        return
    room_alias = getattr(args, 'room_name', None)

    if not rooms:
        console.print("[yellow]No active public rooms. Run [bold]enchat[/] to create one.[/]")
        return

    if not room_alias:
        room_alias = Prompt.ask(
            "Which public room would you like to join?",
            choices=[room.name for room in rooms],
        )

    public_room = public_rooms.find_room(rooms, room_alias)
    if public_room is None:
        console.print(f"[bold red]Error: Public room '{room_alias}' not found.[/]")
        console.print(
            f"Available public rooms are: [cyan]{', '.join(room.name for room in rooms)}[/]"
        )
        return

    console.print(
        Text.from_markup(f"Joining public room: [bold cyan]{public_room.name}[/].\n"),
        justify="center",
    )
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
    
    console.print(f"\n[green]Connecting to '{public_room.name}' as '{display_name}'...[/]")
    start_chat(
        public_room.topic,
        display_name,
        public_room.secret,
        server,
        [],
        is_public=True,
        is_tor=args.tor,
        room_label=public_room.name,
        public_room=public_room,
    )

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
    implicit_start = len(sys.argv) == 1
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
        help='Name or ID of an active public room. If omitted, a list will be shown.'
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

    if args.tor:
        network.configure_tor()
        
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
    room, nick, secret, server_conf = config.load_conf()
    server = args.server or server_conf
    
    if implicit_start or not all((room, nick, server)):
        room, nick, secret, server = first_run(
            args, (room, nick, secret, server)
        )

    if room and nick and server:
        start_chat(room, nick, secret, server, [], is_tor=args.tor)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Exited gracefully.[/]")
        sys.exit(0)
