import time
from cryptography.fernet import Fernet

# In-memory storage for session keys: {room: (key, creation_timestamp)}
_active_sessions = {}
SESSION_KEY_ROTATION_INTERVAL = 300  # 5 minutes

def generate_session_key() -> bytes:
    """Generates a new Fernet key."""
    return Fernet.generate_key()

def set_session_key(room: str, key: bytes):
    """Stores a new session key for a room."""
    _active_sessions[room] = (key, int(time.time()))

def get_session_key(room: str) -> bytes | None:
    """Retrieves the current session key for a room."""
    return _active_sessions.get(room, (None, 0))[0]

def should_rotate_key(room: str) -> bool:
    """Checks if the session key for a room needs to be rotated."""
    if room not in _active_sessions:
        return True  # No key exists yet
    _, timestamp = _active_sessions[room]
    return (time.time() - timestamp) > SESSION_KEY_ROTATION_INTERVAL

def encrypt_with_session(data: str, session_key: bytes) -> str:
    """Encrypts data with the session key."""
    f = Fernet(session_key)
    return f.encrypt(data.encode()).decode()

def decrypt_with_session(token: str, session_key: bytes) -> str:
    """Decrypts data with the session key."""
    f = Fernet(session_key)
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        return ""

def encrypt_session_key(session_key: bytes, room_key_fernet: Fernet) -> str:
    """Encrypts a session key with the main room key."""
    return room_key_fernet.encrypt(session_key).decode()

def decrypt_session_key(encrypted_key: str, room_key_fernet: Fernet) -> bytes | None:
    """Decrypts a session key with the main room key."""
    try:
        return room_key_fernet.decrypt(encrypted_key.encode())
    except Exception:
        return None
