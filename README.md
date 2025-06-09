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

Clone the repository and run one of the installer scripts:

```bash
git clone https://github.com/sudodevdante/enchat.git
cd enchat

# Standard installation (start Enchat with `enchat`)
./install-enchat.sh

# Or install with wipe integration (adds `enchat wipe` command)
./install-enchat-wipe.sh
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

Start the chat or wipe saved traces with the following commands:

```bash
# If installed via the installer script:
enchat           # start Enchat
enchat wipe      # wipe all Enchat traces

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

Commands can be run via the `enchat` launcher or directly with Python:

```bash
# Show help for available options
enchat --help

# Delete saved settings and prompt for reconfiguration
enchat --reset
# or:
python enchat.py --reset

# Securely remove all Enchat traces (configuration, shell history entries, and terminal scrollback)
enchat wipe
```

- `--reset`: delete saved settings (`~/.enchat.conf`) and prompt for new configuration.
- `wipe`: securely remove all Enchat traces (config file, shell history entries, and terminal scrollback).

### In-chat commands

- `/exit`: leave the chat and exit
- `/clear`: clear your terminal screen

## How it works

Enchat pushes and listens for messages via `https://ntfy.sh/<room>`. Messages are encrypted client-side with symmetric encryption (Fernet). Only participants with the same room name and passphrase can decrypt and read the messages.

## Security & privacy

### Configuration & saved settings

Enchat stores your room name, nickname, and encryption passphrase in plain text in `~/.enchat.conf` for auto-reconnection. To protect your passphrase, restrict access to this file:

```bash
chmod 600 ~/.enchat.conf
```

If you prefer not to save your passphrase, choose "no" when prompted and you'll be asked each time.

You can remove saved settings with `enchat --reset`, or perform a full wipe of all traces (including shell history) with `enchat wipe`.

### End-to-end encryption

Enchat uses the Python `cryptography` library's Fernet implementation for client-side encryption and authentication. A symmetric key is derived from your passphrase using SHA-256, and messages are encrypted with AES in CBC mode and authenticated with HMAC-SHA256. The ntfy.sh service only sees encrypted payloads; your passphrase is never transmitted or stored on any server.