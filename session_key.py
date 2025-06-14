"""
Session key management for Enchat
Implements Forward Secrecy via temporary session keys
"""
import os
import time
import base64
from typing import Optional, Dict, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Session key storage (in-memory only for security)
_active_sessions: Dict[str, Tuple[bytes, float]] = {}  # room -> (key, timestamp)
SESSION_KEY_ROTATION_INTERVAL = 3600  # 1 hour

# Public room configuration
PUBLIC_ROOMS = {
    "public": {
        "name": "public",
        "description": "Public chat room - messages are NOT encrypted",
        "warning": "⚠️ This is a public room. Messages are NOT encrypted. Do not share sensitive information."
    }
}

def normalize_public_room_name(room: str) -> str:
    """Normalize public room name to ensure all users join the same room"""
    room = room.lower().strip()
    if room == "public" or room.startswith("public-"):
        return "public"
    return room

def is_public_room(room: str) -> bool:
    """Check if a room is a public room"""
    normalized = normalize_public_room_name(room)
    return normalized in PUBLIC_ROOMS

def get_public_room_info(room: str) -> Optional[dict]:
    """Get information about a public room"""
    normalized = normalize_public_room_name(room)
    return PUBLIC_ROOMS.get(normalized)

def generate_session_key() -> bytes:
    """Generate a new random session key"""
    return Fernet.generate_key()

def get_session_key(room: str) -> Optional[bytes]:
    """Get current session key for room if exists and not expired"""
    # For public rooms, use a static key
    if is_public_room(room):
        return base64.urlsafe_b64encode(b"public_room_static_key_do_not_use_for_private_rooms!")
    
    if room in _active_sessions:
        key, timestamp = _active_sessions[room]
        if time.time() - timestamp < SESSION_KEY_ROTATION_INTERVAL:
            return key
        del _active_sessions[room]  # Expired key
    return None

def set_session_key(room: str, key: bytes):
    """Set session key for room with current timestamp"""
    if not is_public_room(room):  # Don't store keys for public rooms
        _active_sessions[room] = (key, time.time())

def encrypt_session_key(session_key: bytes, room_key: Fernet) -> str:
    """Encrypt session key with room key for secure transmission"""
    return room_key.encrypt(session_key).decode()

def decrypt_session_key(encrypted_key: str, room_key: Fernet) -> Optional[bytes]:
    """Decrypt session key using room key"""
    try:
        return room_key.decrypt(encrypted_key.encode())
    except Exception:
        return None

def encrypt_with_session(message: str, session_key: bytes) -> str:
    """Encrypt message using session key"""
    f = Fernet(session_key)
    return f.encrypt(message.encode()).decode()

def decrypt_with_session(encrypted: str, session_key: bytes) -> Optional[str]:
    """Decrypt message using session key"""
    try:
        f = Fernet(session_key)
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return None

def should_rotate_key(room: str) -> bool:
    """Check if session key should be rotated"""
    if is_public_room(room):  # Public rooms don't need key rotation
        return False
    if room not in _active_sessions:
        return True
    _, timestamp = _active_sessions[room]
    return time.time() - timestamp >= SESSION_KEY_ROTATION_INTERVAL 