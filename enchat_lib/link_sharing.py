"""
Handles the creation and consumption of temporary, one-time-use links for sharing room credentials.
"""

import base64
from cryptography.fernet import Fernet
import requests
import json

# The base URL for the link sharing server.
# For local testing, this will point to our Flask server.
# In production, this would be the public URL of our deployed service.
LINK_SERVER_URL = "https://share.enchat.io"

def _parse_time_to_seconds(time_str: str) -> int | None:
    """Converts a human-readable time string like '10m', '2h', '1d' into seconds."""
    time_str = time_str.lower()
    if time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('d'):
        return int(time_str[:-1]) * 86400
    return None

def generate_link_components(room_name: str, room_secret: str, server_url: str) -> tuple[str, str]:
    """
    Generates the core components for a secure, one-time-use link.
    This now includes the server_url in the encrypted payload.
    """
    ephemeral_key = Fernet.generate_key()
    f = Fernet(ephemeral_key)

    # Include all necessary credentials in the payload
    plaintext_credentials = f"{room_name}|{server_url}|{room_secret}"

    encrypted_payload = f.encrypt(plaintext_credentials.encode('utf-8'))

    encoded_payload = base64.urlsafe_b64encode(encrypted_payload).decode('utf-8')
    encoded_key = base64.urlsafe_b64encode(ephemeral_key).decode('utf-8')
    
    return encoded_payload, encoded_key

def create_remote_session(payload: str, ttl: int | None = None, uses: int | None = None) -> str | None:
    """
    Posts the encrypted payload to the link server to create a new session.

    Args:
        payload: The URL-safe base64 encoded encrypted room credentials.
        ttl: The time-to-live for the link in seconds.
        uses: The number of times the link can be used.

    Returns:
        The session ID if successful, otherwise None.
    """
    try:
        request_data = {"payload": payload}
        if ttl is not None:
            request_data["ttl"] = ttl
        if uses is not None:
            request_data["uses"] = uses

        response = requests.post(f"{LINK_SERVER_URL}/create", json=request_data, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("session_id")
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None

def get_remote_payload(session_id: str) -> str | None:
    """
    Retrieves the encrypted payload from the link server for a given session ID.
    """
    try:
        response = requests.get(f"{LINK_SERVER_URL}/get/{session_id}", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("payload")
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None

def construct_share_url(session_id: str, key: str) -> str:
    """
    Constructs the final, user-shareable URL.
    """
    return f"{LINK_SERVER_URL}/join#{session_id}:{key}"

def parse_share_url(url: str) -> tuple[str, str] | None:
    """
    Parses a share URL to extract the session ID and key.
    Returns None if the URL is malformed.
    """
    try:
        _, fragment = url.split('/join#')
        session_id, key = fragment.split(':')
        return session_id, key
    except (ValueError, IndexError):
        return None

def decrypt_credentials(encrypted_payload: str, ephemeral_key: str) -> tuple[str, str, str]:
    """
    Decrypts the room credentials received from the link server.
    Returns room_name, server_url, and room_secret.
    """
    key_bytes = base64.urlsafe_b64decode(ephemeral_key)
    payload_bytes = base64.urlsafe_b64decode(encrypted_payload)
    
    f = Fernet(key_bytes)
    
    decrypted_bytes = f.decrypt(payload_bytes)
    decrypted_str = decrypted_bytes.decode('utf-8')
    
    # Split back into the three components
    room_name, server_url, room_secret = decrypted_str.split('|', 2)
    
    return room_name, server_url, room_secret 