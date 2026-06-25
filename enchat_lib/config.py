import os
import sys
import subprocess
from .constants import CONF_FILE, DEFAULT_NTFY, KEYRING_AVAILABLE

if KEYRING_AVAILABLE:
    import keyring

def save_passphrase_keychain(room: str, secret: str):
    """Saves a passphrase to the system keychain."""
    if KEYRING_AVAILABLE:
        try:
            keyring.set_password("enchat", f"room_{room}", secret)
        except Exception:
            pass

def load_passphrase_keychain(room: str) -> str:
    """Loads a passphrase from the system keychain."""
    if KEYRING_AVAILABLE:
        try:
            return keyring.get_password("enchat", f"room_{room}") or ""
        except Exception:
            pass
    return ""

def wipe_keychain_entries():
    """
    Remove only Enchat-related entries from system keychain/keyring.
    Returns (success, warnings)
    """
    warnings = []
    try:
        if not KEYRING_AVAILABLE:
            warnings.append("Keyring library not available, cannot wipe entries.")
            return False, warnings

        if sys.platform == "darwin":
            # macOS: Use 'security' command-line tool
            result = subprocess.run(['security', 'find-generic-password', '-s', 'enchat'], capture_output=True, text=True)
            for line in result.stderr.splitlines():
                if "service=" in line:
                    service = line.split('service=')[1].strip().strip('"')
                    if 'room_' in service:
                        subprocess.run(['security', 'delete-generic-password', '-s', 'enchat', '-a', service], check=True)
        
        elif sys.platform == "linux":
            # This is a best-effort approach for Secret-Tool
            if subprocess.run(['which', 'secret-tool'], capture_output=True).returncode == 0:
                result = subprocess.run(['secret-tool', 'search', 'application', 'enchat'], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if line.strip():
                         # secret-tool lacks a direct delete, so we clear the password
                         keyring.delete_password("enchat", line.strip())
            else:
                warnings.append("secret-tool not found. Cannot clear Linux keyring entries automatically.")
        
        elif sys.platform == "win32":
             # Windows uses Credential Locker, which keyring abstracts
             # We find all secrets for the service and delete them.
             for room_config in keyring.get_credential("enchat", None):
                 keyring.delete_password("enchat", room_config.username)

    except Exception as e:
        warnings.append(f"An error occurred while clearing keychain entries: {e}")
    
    return len(warnings) == 0, warnings

def save_conf(room: str, nick: str, secret: str, server: str):
    """Save non-sensitive settings; passphrases belong in the system keychain."""
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        f.write(f"{room}\n{nick}\n\n{server}\n")
    try:
        os.chmod(CONF_FILE, 0o600)
    except Exception:
        pass

def load_conf():
    """Loads the configuration from a file."""
    if not os.path.exists(CONF_FILE):
        return None, None, None, None
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            room, nick, secret, *rest = [l.strip() for l in f.readlines()]
        server = rest[0] if rest else DEFAULT_NTFY
        if not secret:
            secret = load_passphrase_keychain(room)
        return room, nick, secret, server
    except Exception:
        return None, None, None, None
