#!/usr/bin/env python3
import requests, base64, hashlib, threading, signal, sys, os
from colorama import Fore, Style, init
from cryptography.fernet import Fernet, InvalidToken
import getpass

init(autoreset=True)

def gen_key(secret):
    h = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(h)

def notify(msg):
    if sys.platform.startswith('linux'):
        os.system(f'notify-send "Enchat" "{msg}"')
    elif sys.platform == 'darwin':
        os.system(f'''osascript -e 'display notification "{msg}" with title "Enchat"' ''')

def print_system(msg):
    print(Fore.YELLOW + Style.BRIGHT + f"[SYSTEEM] {msg}")

def print_user(user, msg, you=False):
    color = Fore.CYAN if not you else Fore.GREEN
    print(f"{color}{user}:{Style.RESET_ALL} {msg}")

def encrypt_msg(msg, fernet):
    return fernet.encrypt(msg.encode()).decode()

def decrypt_msg(token, fernet):
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None

def listen(room, nick, fernet, stop_event):
    url = f"https://ntfy.sh/{room}/raw"
    last_msgs = set()
    try:
        with requests.get(url, stream=True, timeout=10) as r:
            for line in r.iter_lines():
                if stop_event.is_set():
                    break
                if not line: continue
                line = line.decode()
                msg_hash = hashlib.sha256(line.encode()).hexdigest()
                if msg_hash in last_msgs:
                    continue
                last_msgs.add(msg_hash)
                if len(last_msgs) > 500:
                    last_msgs = set(list(last_msgs)[-250:])
                if line.startswith("[SYSTEM]["):
                    who = line.split(']')[1][1:]
                    what = line.split('] ')[-1]
                    if who != nick:
                        if what == "joined":
                            print_system(f"{Fore.CYAN}{who}{Style.RESET_ALL} is de chat binnengekomen.")
                            notify(f"{who} is de chat binnengekomen.")
                        elif what == "left":
                            print_system(f"{Fore.RED}{who}{Style.RESET_ALL} heeft de chat verlaten.")
                            notify(f"{who} heeft de chat verlaten.")
                    continue
                if not line.startswith("[") or "] " not in line:
                    continue
                sender = line.split("]")[0][1:]
                data = "]".join(line.split("]")[1:]).strip()
                if sender == nick:
                    continue
                dec = decrypt_msg(data, fernet)
                if dec:
                    print_user(sender, dec)
                    notify(f"{sender}: {dec}")
                else:
                    if data.startswith("U2FsdGVk") or data.startswith("gAAAA"):
                        print_user(sender, "[Onleesbaar of verkeerde code]")
    except Exception as e:
        print(Fore.RED + f"\nVerbinding met ntfy.sh verbroken: {e}\nHerstart het script om opnieuw te verbinden." + Style.RESET_ALL)
        stop_event.set()
        sys.exit(0)

def send_msg(room, msg, nick, fernet):
    url = f"https://ntfy.sh/{room}"
    enc = encrypt_msg(msg, fernet)
    requests.post(url, data=f"[{nick}] {enc}")

def send_system(room, nick, msg):
    url = f"https://ntfy.sh/{room}"
    requests.post(url, data=f"[SYSTEM][{nick}] {msg}")

def main():
    print(Fore.MAGENTA + Style.BRIGHT + "== ENCRYPTED TERMINAL CHAT ==")
    room = input("Roomnaam (uniek, geheim): ").strip()
    nick = input("Jouw nickname: ").strip()
    secret = getpass.getpass("Encryptiecode (niet zichtbaar): ").strip()
    key = gen_key(secret)
    fernet = Fernet(key)
    print_system(f"Je joined room {room}. Type /exit om te stoppen, /clear om scherm te wissen.")
    send_system(room, nick, "joined")
    stop_event = threading.Event()
    t = threading.Thread(target=listen, args=(room, nick, fernet, stop_event), daemon=True)
    t.start()
    def sigint_handler(sig, frame):
        send_system(room, nick, "left")
        print_system("Je verlaat de chat.")
        stop_event.set()
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)
    try:
        while not stop_event.is_set():
            msg = input(Fore.GREEN + "> " + Style.RESET_ALL)
            if msg == "/exit":
                send_system(room, nick, "left")
                print_system("Je verlaat de chat.")
                stop_event.set()
                sys.exit(0)
            elif msg == "/clear":
                os.system('clear')
            elif msg.strip():
                send_msg(room, msg, nick, fernet)
    except (KeyboardInterrupt, EOFError):
        send_system(room, nick, "left")
        print_system("Je verlaat de chat.")
        stop_event.set()
        sys.exit(0)

if __name__ == "__main__":
    main()

