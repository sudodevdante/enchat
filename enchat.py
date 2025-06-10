#!/usr/bin/env python3
import os
import sys
import time
import signal
import base64
import hashlib
import threading
import argparse
import requests
from getpass import getpass
from colorama import init, Fore, Style, Back
from cryptography.fernet import Fernet, InvalidToken
from shutil import which
import subprocess
from datetime import datetime

init(autoreset=True)
CONF_FILE = os.path.expanduser("~/.enchat.conf")
DEFAULT_NTFY_SERVER = "https://ntfy.sh"

# Enhanced UI Constants
BORDER_CHAR = "─"
CORNER_CHAR = "┌┐└┘"
SIDE_CHAR = "│"
MAX_MESSAGE_LENGTH = 500
STATUS_CONNECTED = "🟢"
STATUS_CONNECTING = "🟡"
STATUS_DISCONNECTED = "🔴"

class ChatUI:
    def __init__(self):
        self.terminal_width = os.get_terminal_size().columns
        self.status = STATUS_CONNECTING
        
    def get_timestamp(self):
        return datetime.now().strftime("%H:%M:%S")
    
    def print_header(self):
        width = self.terminal_width
        header = "ENCRYPTED TERMINAL CHAT"
        padding = (width - len(header) - 2) // 2
        
        print(Fore.CYAN + Style.BRIGHT + "┌" + "─" * (width - 2) + "┐")
        print("│" + " " * padding + header + " " * (width - len(header) - padding - 2) + "│")
        print("└" + "─" * (width - 2) + "┘" + Style.RESET_ALL)
        print()
    
    def print_status_bar(self, room, nick, ntfy_server):
        width = self.terminal_width
        server_display = ntfy_server.replace("https://", "").replace("http://", "")
        status_text = f"{self.status} {room} | {nick} | {server_display}"
        
        if len(status_text) > width - 4:
            status_text = status_text[:width - 7] + "..."
        
        padding = width - len(status_text) - 2
        print(Fore.BLUE + "┌" + "─" * (width - 2) + "┐")
        print("│" + status_text + " " * padding + "│" + Style.RESET_ALL)
        print(Fore.BLUE + "└" + "─" * (width - 2) + "┘" + Style.RESET_ALL)
    
    def print_system_message(self, msg, msg_type="info"):
        timestamp = self.get_timestamp()
        
        if msg_type == "join":
            icon = "→"
            color = Fore.GREEN
        elif msg_type == "leave": 
            icon = "←"
            color = Fore.RED
        elif msg_type == "error":
            icon = "⚠"
            color = Fore.YELLOW
        else:
            icon = "ℹ"
            color = Fore.CYAN
            
        print(f"{Fore.BLACK + Style.BRIGHT}[{timestamp}]{Style.RESET_ALL} {color}{icon} {msg}{Style.RESET_ALL}")
    
    def print_user_message(self, user, msg, is_own=False):
        timestamp = self.get_timestamp()
        
        # Truncate long messages
        if len(msg) > MAX_MESSAGE_LENGTH:
            msg = msg[:MAX_MESSAGE_LENGTH - 3] + "..."
        
        if is_own:
            user_color = Fore.GREEN + Style.BRIGHT
            msg_color = Style.RESET_ALL
        else:
            user_color = Fore.MAGENTA + Style.BRIGHT  
            msg_color = Style.RESET_ALL
            
        # Format: [timestamp] username: message
        print(f"{Fore.BLACK + Style.BRIGHT}[{timestamp}]{Style.RESET_ALL} {user_color}{user}:{Style.RESET_ALL} {msg_color}{msg}")
    
    def print_connection_status(self, status, details=""):
        if status == "connecting":
            self.status = STATUS_CONNECTING
            self.print_system_message(f"Connecting to server... {details}", "info")
        elif status == "connected":
            self.status = STATUS_CONNECTED
            self.print_system_message(f"Connected successfully! {details}", "info")
        elif status == "disconnected":
            self.status = STATUS_DISCONNECTED
            self.print_system_message(f"Connection lost. {details}", "error")
        elif status == "reconnecting":
            self.status = STATUS_CONNECTING
            self.print_system_message(f"Reconnecting... {details}", "info")
    
    def print_input_prompt(self):
        return f"{Fore.GREEN + Style.BRIGHT}💬 > {Style.RESET_ALL}"
    
    def print_loading_animation(self, text, duration=2):
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        start_time = time.time()
        i = 0
        
        while time.time() - start_time < duration:
            frame = frames[i % len(frames)]
            print(f"\r{Fore.CYAN}{frame} {text}...{Style.RESET_ALL}", end="", flush=True)
            time.sleep(0.1)
            i += 1
        print(f"\r{' ' * (len(text) + 10)}\r", end="")  # Clear the line

ui = ChatUI()

def gen_key(secret: str) -> bytes:
    h = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(h)

def save_conf(room: str, nick: str, secret: str, ntfy_server: str = DEFAULT_NTFY_SERVER):
    with open(CONF_FILE, "w") as f:
        f.write(f"{room}\n{nick}\n{secret}\n{ntfy_server}\n")

def load_conf():
    try:
        with open(CONF_FILE) as f:
            lines = [l.strip() for l in f.readlines()]
            if len(lines) >= 3:
                room = lines[0]
                nick = lines[1] 
                secret = lines[2]
                ntfy_server = lines[3] if len(lines) >= 4 else DEFAULT_NTFY_SERVER
                return room, nick, secret, ntfy_server
    except Exception:
        pass
    return None, None, None, DEFAULT_NTFY_SERVER

def notify(msg: str):
    # Linux: only if notify-send exists; suppress all output/errors
    if sys.platform.startswith("linux") and which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "Enchat", msg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            pass
    # macOS: use osascript if available, also silenced
    elif sys.platform == "darwin" and which("osascript"):
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{msg}" with title "Enchat"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            pass

def encrypt_msg(msg: str, fernet: Fernet) -> str:
    return fernet.encrypt(msg.encode()).decode()

def decrypt_msg(token: str, fernet: Fernet) -> str or None:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None

def listen(room: str, nick: str, fernet: Fernet, stop_event: threading.Event, ntfy_server: str):
    url = f"{ntfy_server}/{room}/raw"
    seen = set()
    connection_attempts = 0
    
    while not stop_event.is_set():
        try:
            if connection_attempts > 0:
                ui.print_connection_status("reconnecting", f"Attempt #{connection_attempts}")
            
            with requests.get(url, stream=True, timeout=70) as resp:
                if connection_attempts > 0:
                    ui.print_connection_status("connected", "Reconnected successfully")
                connection_attempts = 0
                
                for line in resp.iter_lines():
                    if stop_event.is_set(): break
                    if not line: continue
                    line = line.decode()
                    h = hashlib.sha256(line.encode()).hexdigest()
                    if h in seen: continue
                    seen.add(h)
                    if len(seen) > 500:
                        seen = set(list(seen)[-250:])
                    
                    # System events
                    if line.startswith("[SYSTEM]["):
                        who = line.split("]")[1][1:]
                        what = line.split("] ")[-1]
                        if who != nick:
                            if what == "joined":
                                ui.print_system_message(f"{who} joined the chat", "join")
                                notify(f"{who} joined")
                            elif what == "left":
                                ui.print_system_message(f"{who} left the chat", "leave")
                                notify(f"{who} left")
                        continue
                    
                    # Chat messages
                    if not line.startswith("[") or "] " not in line:
                        continue
                    sender = line.split("]")[0][1:]
                    data   = "]".join(line.split("]")[1:]).strip()
                    
                    plain = decrypt_msg(data, fernet)
                    if plain is not None:
                        is_own_message = (sender == nick)
                        if not is_own_message:  # Only show messages from others
                            ui.print_user_message(sender, plain, is_own=False)
                            notify(f"{sender}: {plain}")
                    else:
                        if data.startswith(("U2FsdGVk","gAAAA")):
                            ui.print_user_message(sender, "[🔒 Encrypted message - wrong passphrase]")
                            
        except Exception as e:
            if not stop_event.is_set():
                connection_attempts += 1
                ui.print_connection_status("disconnected", f"({str(e)[:50]})")
                time.sleep(min(2 ** min(connection_attempts, 5), 30))  # Exponential backoff

def send_msg(room: str, msg: str, nick: str, fernet: Fernet, ntfy_server: str):
    try:
        enc = encrypt_msg(msg, fernet)
        response = requests.post(f"{ntfy_server}/{room}", data=f"[{nick}] {enc}", timeout=10)
        if response.status_code != 200:
            ui.print_system_message(f"Failed to send message (HTTP {response.status_code})", "error")
    except Exception as e:
        ui.print_system_message(f"Failed to send message: {str(e)[:50]}", "error")

def send_system(room: str, nick: str, what: str, ntfy_server: str):
    try:
        requests.post(f"{ntfy_server}/{room}", data=f"[SYSTEM][{nick}] {what}", timeout=10)
    except Exception:
        pass  # Silent fail for system messages

def setup_initial_config(args):
    """Handle initial configuration with enhanced UI"""
    os.system("clear")
    ui.print_header()
    
    print(f"{Fore.CYAN}Welcome to Enchat! Let's set up your encrypted chat.{Style.RESET_ALL}\n")
    
    # Room configuration
    while True:
        room = input(f"{Fore.YELLOW}🏠 Room name (unique, secret): {Style.RESET_ALL}").strip()
        if room and len(room) >= 3:
            break
        print(f"{Fore.RED}Please enter a room name with at least 3 characters.{Style.RESET_ALL}")
    
    # Nickname configuration  
    while True:
        nick = input(f"{Fore.YELLOW}👤 Your nickname: {Style.RESET_ALL}").strip()
        if nick and len(nick) >= 2:
            break
        print(f"{Fore.RED}Please enter a nickname with at least 2 characters.{Style.RESET_ALL}")
    
    # Encryption passphrase
    while True:
        secret = getpass(f"{Fore.YELLOW}🔐 Encryption passphrase (hidden): {Style.RESET_ALL}").strip()
        if secret and len(secret) >= 6:
            break
        print(f"{Fore.RED}Please enter a passphrase with at least 6 characters.{Style.RESET_ALL}")
    
    # Server configuration
    ntfy_server = DEFAULT_NTFY_SERVER
    if not args.server:
        server_input = input(f"{Fore.YELLOW}🌐 ntfy server URL (press Enter for default {DEFAULT_NTFY_SERVER}): {Style.RESET_ALL}").strip()
        if server_input:
            ntfy_server = server_input.rstrip('/')
    else:
        ntfy_server = args.server.rstrip('/')
    
    # Save configuration
    yn = input(f"{Fore.YELLOW}💾 Save settings for auto-reconnect? [Y/n]: {Style.RESET_ALL}").strip() or "Y"
    if yn.lower().startswith("y"):
        save_conf(room, nick, secret, ntfy_server)
        print(f"{Fore.GREEN}✅ Settings saved to {CONF_FILE}{Style.RESET_ALL}")
    
    return room, nick, secret, ntfy_server

def main():
    parser = argparse.ArgumentParser(description="Encrypted terminal chat using ntfy")
    parser.add_argument("--reset", action="store_true",
                        help="Clear saved settings and start fresh")
    parser.add_argument("--server", type=str,
                        help="Use custom ntfy server (e.g., https://your-ntfy.example.com)")
    args = parser.parse_args()

    if args.reset and os.path.exists(CONF_FILE):
        os.remove(CONF_FILE)
        print(f"{Fore.GREEN}✅ Settings cleared. Restart to configure again.{Style.RESET_ALL}")
        sys.exit(0)

    room, nick, secret, ntfy_server = load_conf()
    
    # Override with command line server if provided
    if args.server:
        ntfy_server = args.server.rstrip('/')
    
    # Initial setup if no configuration exists
    if not all([room, nick, secret]):
        room, nick, secret, ntfy_server = setup_initial_config(args)
    else:
        os.system("clear")
        ui.print_header()
        print(f"{Fore.GREEN}✨ Welcome back, {Style.BRIGHT}{nick}{Style.RESET_ALL}{Fore.GREEN}!{Style.RESET_ALL}")
        server_display = ntfy_server.replace("https://", "").replace("http://", "")
        print(f"{Fore.CYAN}📡 Connecting to room '{room}' via {server_display}...{Style.RESET_ALL}\n")

    key = gen_key(secret)
    fernet = Fernet(key)

    # Show connection status
    ui.print_connection_status("connecting", "Establishing secure connection...")
    ui.print_loading_animation("Connecting", 1)
    
    print()
    ui.print_status_bar(room, nick, ntfy_server)
    print()
    
    # Join the room
    ui.print_system_message(f"Joined room '{room}' • Type /exit to quit, /clear to clear screen", "info")
    send_system(room, nick, "joined", ntfy_server)
    
    # Start listening thread
    stop_event = threading.Event()
    t = threading.Thread(target=listen,
                         args=(room, nick, fernet, stop_event, ntfy_server),
                         daemon=True)
    t.start()
    
    # Set connection status to connected after starting listener
    time.sleep(0.5)
    ui.print_connection_status("connected", "Ready to chat!")
    print()

    def on_exit(sig, frame):
        print(f"\n{Fore.YELLOW}👋 Leaving chat...{Style.RESET_ALL}")
        send_system(room, nick, "left", ntfy_server)
        ui.print_system_message("You left the chat. Goodbye!", "leave")
        stop_event.set()
        sys.exit(0)
    signal.signal(signal.SIGINT, on_exit)

    # Main chat loop
    while not stop_event.is_set():
        try:
            msg = input(ui.print_input_prompt())
        except (EOFError, KeyboardInterrupt):
            on_exit(None, None)
            
        if msg == "/exit":
            on_exit(None, None)
        elif msg == "/clear":
            os.system("clear")
            ui.print_header()
            ui.print_status_bar(room, nick, ntfy_server)
            print()
            continue
        elif msg == "/help":
            print(f"\n{Fore.CYAN}📖 Available commands:{Style.RESET_ALL}")
            print(f"  {Fore.GREEN}/exit{Style.RESET_ALL}  - Leave the chat")
            print(f"  {Fore.GREEN}/clear{Style.RESET_ALL} - Clear the screen") 
            print(f"  {Fore.GREEN}/help{Style.RESET_ALL}  - Show this help\n")
            continue
        elif msg.strip():
            if len(msg) > MAX_MESSAGE_LENGTH:
                ui.print_system_message(f"Message too long ({len(msg)}/{MAX_MESSAGE_LENGTH} characters)", "error")
                continue
            # Clear the entire input line using ANSI escape codes
            print("\033[1A\033[2K", end="")  # Move up one line and clear it
            ui.print_user_message(nick, msg, is_own=True)
            send_msg(room, msg, nick, fernet, ntfy_server)

if __name__ == "__main__":
    main()