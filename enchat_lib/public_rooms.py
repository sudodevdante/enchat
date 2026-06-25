"""Ephemeral public-room discovery over an ntfy relay.

Directory records are encrypted to keep room credentials opaque to a passive
relay. The directory key ships with Enchat, so public rooms provide discovery
and transport encryption, not access control or participant authentication.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Iterable

import requests
from cryptography.fernet import Fernet, InvalidToken

DIRECTORY_TOPIC = "enchat-public-directory-v2-49d30c7b"
DIRECTORY_KEY = b"JeqoLqbR_HOBB_7_iL_J46R5hciYLWgZjfSnz2eVO5w="
DIRECTORY_PREFIX = "ROOM2:"
LEASE_SECONDS = 105
LEASE_REFRESH_SECONDS = 75
DIRECTORY_LOOKBACK = "3m"
MAX_DIRECTORY_ROOMS = 50


class DirectoryUnavailable(RuntimeError):
    """Raised when the relay directory cannot be queried."""


@dataclass(frozen=True)
class PublicRoom:
    room_id: str
    name: str
    topic: str
    secret: str
    expires_at: int = 0


def create_room(name: str) -> PublicRoom:
    """Create unguessable relay credentials for a new public room."""
    cleaned = _clean_name(name)
    if not cleaned:
        raise ValueError("Room name must contain a visible character.")
    room_id = base64.urlsafe_b64encode(os.urandom(9)).decode().rstrip("=")
    topic_suffix = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip("=")
    secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
    return PublicRoom(
        room_id=room_id,
        name=cleaned,
        topic=f"enchat-public-{topic_suffix}",
        secret=secret,
    )


def encode_announcement(room: PublicRoom) -> str:
    record = {
        "v": 2,
        "id": room.room_id,
        "name": room.name,
        "topic": room.topic,
        "secret": room.secret,
        "lease": LEASE_SECONDS,
    }
    token = Fernet(DIRECTORY_KEY).encrypt(
        json.dumps(record, separators=(",", ":")).encode()
    ).decode()
    return f"{DIRECTORY_PREFIX}{token}"


def decode_announcement(
    message: str,
    issued_at: int | None = None,
    now: int | None = None,
) -> PublicRoom | None:
    if not isinstance(message, str) or not message.startswith(DIRECTORY_PREFIX):
        return None
    try:
        plain = Fernet(DIRECTORY_KEY).decrypt(
            message[len(DIRECTORY_PREFIX):].encode()
        )
        record = json.loads(plain)
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not _valid_record(record):
        return None
    timestamp = int(time.time()) if now is None else int(now)
    issued = timestamp if issued_at is None else int(issued_at)
    expires_at = issued + record["lease"]
    if expires_at <= timestamp:
        return None
    return PublicRoom(
        room_id=record["id"],
        name=record["name"],
        topic=record["topic"],
        secret=record["secret"],
        expires_at=expires_at,
    )


def _transport(session=None):
    if session is not None:
        return session
    # Import lazily to avoid a module cycle and share Enchat's Tor-aware session.
    from .network import session as network_session

    return network_session


def publish_room(room: PublicRoom, server: str, session=None) -> bool:
    """Publish one lease renewal for a public room."""
    try:
        response = _transport(session).post(
            f"{server.rstrip('/')}/{DIRECTORY_TOPIC}",
            data=encode_announcement(room),
            timeout=8,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def list_active_rooms(server: str, session=None) -> list[PublicRoom]:
    """Read recent leases, deduplicate them, and return currently active rooms."""
    try:
        response = _transport(session).get(
            f"{server.rstrip('/')}/{DIRECTORY_TOPIC}/json",
            params={"poll": "1", "since": DIRECTORY_LOOKBACK},
            headers={"Accept": "application/x-ndjson"},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DirectoryUnavailable("Public directory is unavailable.") from exc

    latest: dict[str, PublicRoom] = {}
    now = int(time.time())
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict) or event.get("event") != "message":
                continue
            issued_at = event.get("time")
            if not isinstance(issued_at, int) or isinstance(issued_at, bool):
                continue
            room = decode_announcement(
                event.get("message"), issued_at=issued_at, now=now
            )
            if room and (
                room.room_id not in latest
                or room.expires_at > latest[room.room_id].expires_at
            ):
                latest[room.room_id] = room
    except requests.RequestException as exc:
        raise DirectoryUnavailable("Public directory is unavailable.") from exc

    rooms = sorted(latest.values(), key=lambda room: room.name.casefold())
    return rooms[:MAX_DIRECTORY_ROOMS]


def maintain_lease(
    room: PublicRoom,
    server: str,
    stop_event: threading.Event,
    session=None,
) -> None:
    """Renew a room while this participant remains connected."""
    while not stop_event.is_set():
        publish_room(room, server, session=session)
        stop_event.wait(LEASE_REFRESH_SECONDS)


def find_room(rooms: Iterable[PublicRoom], name_or_id: str) -> PublicRoom | None:
    wanted = name_or_id.casefold()
    return next(
        (
            room
            for room in rooms
            if room.room_id.casefold() == wanted or room.name.casefold() == wanted
        ),
        None,
    )


def _clean_name(name: str) -> str:
    printable = "".join(
        ch for ch in name if ch.isprintable() and ch not in "[]"
    )
    return re.sub(r"\s+", " ", printable).strip()[:48]


def _valid_record(record) -> bool:
    if not isinstance(record, dict) or record.get("v") != 2:
        return False
    if not isinstance(record.get("id"), str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{12}", record["id"]
    ):
        return False
    if not isinstance(record.get("name"), str) or not 1 <= len(record["name"]) <= 48:
        return False
    if _clean_name(record["name"]) != record["name"]:
        return False
    if not isinstance(record.get("topic"), str) or not re.fullmatch(
        r"enchat-public-[A-Za-z0-9_-]{24}", record["topic"]
    ):
        return False
    if not isinstance(record.get("secret"), str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{43}=", record["secret"]
    ):
        return False
    lease = record.get("lease")
    return lease == LEASE_SECONDS and not isinstance(lease, bool)
