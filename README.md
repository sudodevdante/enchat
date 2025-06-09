# Enchat

Enchat is a simple encrypted terminal chat tool that uses the free `ntfy.sh` service for real-time messaging with end-to-end encryption directly in your terminal.

## Features
- End-to-end symmetric encryption using the `cryptography` package (Fernet)
- No dedicated server required – messages go through `ntfy.sh`
- Automatic reconnect on connection loss
- Desktop notifications on Linux (`notify-send`) and macOS (`osascript`)
- Save chat settings for automatic reconnection
- Simple chat commands: `/exit`, `/clear`
- Command-line option `--reset` to clear saved settings

## Prerequisites
- Python 3.6 or higher
- `pip` (for installing dependencies)
- (Optional) `git`, if you want to use the installer script
- (Optional) Unix-like OS for desktop notifications (Linux, macOS)

## Installation

### Automatic installer (recommended)

Clone the repository and run the installer script:

```bash
git clone https://github.com/sudodevdante/enchat.git
cd enchat
./install-enchat.sh
```

Follow the prompts to choose an install directory, set up a virtual environment, install dependencies, and (optionally) create a global `enchat` command.

### Manual setup

```bash
git clone https://github.com/sudodevdante/enchat.git
cd enchat

# (Optional) Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install requests colorama cryptography

# Make the main script executable
chmod +x enchat.py
```

## Usage

Start the chat with one of the following commands:

```bash
# If installed via the installer script:
enchat

# If using a virtual environment:
source venv/bin/activate
python enchat.py
```

On first run, you'll be prompted for:
1. **Room name** (unique, secret identifier)
2. **Nickname**
3. **Encryption passphrase**

You can choose to save these settings (in `~/.enchat.conf`) for automatic reconnection.

**Note:** All participants must use the exact same room name and encryption passphrase to join the same chat and decrypt each other's messages.

### Command-line options

```bash
python enchat.py --reset
```

- `--reset`: delete saved settings (`~/.enchat.conf`) and start fresh.

### In-chat commands

- `/exit`: leave the chat and exit
- `/clear`: clear your terminal screen

## How it works

Enchat pushes and listens for messages via `https://ntfy.sh/<room>`. Messages are encrypted client-side with symmetric encryption (Fernet). Only participants with the same room name and passphrase can decrypt and read the messages.