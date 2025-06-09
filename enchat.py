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
from colorama import init, Fore, Style
from cryptography.fernet import Fernet, InvalidToken
from shutil import which
import subprocess

init(autoreset=True)
CONF_FILE = os.path.expanduser("~/.enchat.conf")

def gen_key(secret: str) -> bytes:
    h = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(h)

def save_conf(room: str, nick: str, secret: str):
    with open(CONF_FILE, "w") as f:
        f.write(f"{room}\n{nick}\n{secret}\n")

def load_conf():
    try:
        with open(CONF_FILE) as f:
            lines = [l.strip() for l in f.readlines()]
            if len(lines) >= 3:
                return lines[0], lines[1], lines[2]
    except Exception:
        pass
    return None, None, None

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

def print_system(msg: str):
    print(Fore.YELLOW + Style.BRIGHT + f"[SYSTEM] {msg}")

def print_user(user: str, msg: str):
    print(Fore.CYAN + f"{user}:" + Style.RESET_ALL + f" {msg}")

def encrypt_msg(msg: str, fernet: Fernet) -> str:
    return fernet.encrypt(msg.encode()).decode()

def decrypt_msg(token: str, fernet: Fernet) -> str or None:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None

def listen(room: str, nick: str, fernet: Fernet, stop_event: threading.Event):
    url = f"https://ntfy.sh/{room}/raw"
    seen = set()
    while not stop_event.is_set():
        try:
            with requests.get(url, stream=True, timeout=70) as resp:
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
                                print_system(Fore.CYAN + who + Style.RESET_ALL + " joined.")
                                notify(f"{who} joined")
                            elif what == "left":
                                print_system(Fore.RED + who + Style.RESET_ALL + " left.")
                                notify(f"{who} left")
                        continue
                    # Chat messages
                    if not line.startswith("[") or "] " not in line:
                        continue
                    sender = line.split("]")[0][1:]
                    data   = "]".join(line.split("]")[1:]).strip()
                    if sender == nick:
                        continue
                    plain = decrypt_msg(data, fernet)
                    if plain is not None:
                        print_user(sender, plain)
                        notify(f"{sender}: {plain}")
                    else:
                        if data.startswith(("U2FsdGVk","gAAAA")):
                            print_user(sender, "[Unreadable or wrong code]")
        except Exception as e:
            if not stop_event.is_set():
                print(Fore.YELLOW + f"\nConnection lost ({e}). Reconnecting..." + Style.RESET_ALL)
                time.sleep(2)

def send_msg(room: str, msg: str, nick: str, fernet: Fernet):
    enc = encrypt_msg(msg, fernet)
    requests.post(f"https://ntfy.sh/{room}", data=f"[{nick}] {enc}")

def send_system(room: str, nick: str, what: str):
    requests.post(f"https://ntfy.sh/{room}", data=f"[SYSTEM][{nick}] {what}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="Clear saved settings and start fresh")
    args = parser.parse_args()

    if args.reset and os.path.exists(CONF_FILE):
        os.remove(CONF_FILE)
        print(Fore.GREEN + "Settings cleared. Restart to configure again." + Style.RESET_ALL)
        sys.exit(0)

    room, nick, secret = load_conf()
    if not all([room, nick, secret]):
        print(Fore.MAGENTA + Style.BRIGHT + "== ENCRYPTED TERMINAL CHAT ==" + Style.RESET_ALL)
        room   = input("Room name (unique, secret): ").strip()
        nick   = input("Your nickname: ").strip()
        secret = getpass("Encryption code (hidden): ").strip()
        yn = input(Fore.YELLOW + "Save settings for auto-reconnect? [Y/n]: " + Style.RESET_ALL).strip() or "Y"
        if yn.lower().startswith("y"):
            save_conf(room, nick, secret)
            print(Fore.GREEN + "Settings saved." + Style.RESET_ALL)
    else:
        print(Fore.GREEN + f"Welcome back, {nick}! Auto-connecting to '{room}'." + Style.RESET_ALL)

    key    = gen_key(secret)
    fernet = Fernet(key)

    print_system(f"You joined room {room}. Type /exit to quit, /clear to clear screen.")
    send_system(room, nick, "joined")

    stop_event = threading.Event()
    t = threading.Thread(target=listen,
                         args=(room, nick, fernet, stop_event),
                         daemon=True)
    t.start()

    def on_exit(sig, frame):
        send_system(room, nick, "left")
        print_system("You left the chat.")
        stop_event.set()
        sys.exit(0)
    signal.signal(signal.SIGINT, on_exit)

    while not stop_event.is_set():
        try:
            msg = input(Fore.GREEN + "> " + Style.RESET_ALL)
        except (EOFError, KeyboardInterrupt):
            on_exit(None, None)
        if msg == "/exit":
            on_exit(None, None)
        elif msg == "/clear":
            os.system("clear")
            continue
        elif msg.strip():
            send_msg(room, msg, nick, fernet)

if __name__ == "__main__":
    main()