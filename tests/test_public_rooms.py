import json
import threading
import unittest
from unittest.mock import Mock

from enchat_lib import public_rooms


class FakeResponse:
    def __init__(self, lines=(), status_code=200):
        self.lines = list(lines)
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise public_rooms.requests.HTTPError("failed")

    def iter_lines(self, decode_unicode=False):
        return iter(self.lines)


class PublicRoomDirectoryTests(unittest.TestCase):
    def test_created_room_uses_random_internal_credentials(self):
        first = public_rooms.create_room("  Coffee   break  ")
        second = public_rooms.create_room("Coffee break")
        self.assertEqual("Coffee break", first.name)
        self.assertNotEqual(first.room_id, second.room_id)
        self.assertNotEqual(first.topic, second.topic)
        self.assertNotEqual(first.secret, second.secret)
        self.assertNotIn(first.name.lower(), first.topic.lower())

    def test_announcement_round_trip_and_expiry(self):
        room = public_rooms.create_room("Design")
        encoded = public_rooms.encode_announcement(room)
        decoded = public_rooms.decode_announcement(encoded, issued_at=1_000, now=1_010)
        self.assertEqual(room.room_id, decoded.room_id)
        self.assertEqual(room.topic, decoded.topic)
        self.assertIsNone(
            public_rooms.decode_announcement(
                encoded,
                issued_at=1_000,
                now=1_000 + public_rooms.LEASE_SECONDS,
            )
        )

    def test_directory_deduplicates_renewed_leases(self):
        room = public_rooms.create_room("Design")
        messages = [
            public_rooms.encode_announcement(room),
            public_rooms.encode_announcement(room),
        ]
        lines = [
            json.dumps({"event": "message", "time": issued, "message": message})
            for issued, message in zip((2_000, 2_010), messages)
        ]
        session = Mock()
        session.get.return_value = FakeResponse(lines)
        with unittest.mock.patch.object(public_rooms.time, "time", return_value=2_020):
            rooms = public_rooms.list_active_rooms("https://relay", session=session)
        self.assertEqual(1, len(rooms))
        self.assertEqual(2_010 + public_rooms.LEASE_SECONDS, rooms[0].expires_at)
        session.get.assert_called_once()
        self.assertEqual("1", session.get.call_args.kwargs["params"]["poll"])

    def test_publish_uses_directory_topic(self):
        session = Mock()
        session.post.return_value = FakeResponse()
        room = public_rooms.create_room("Design")
        self.assertTrue(public_rooms.publish_room(room, "https://relay/", session))
        self.assertEqual(
            f"https://relay/{public_rooms.DIRECTORY_TOPIC}",
            session.post.call_args.args[0],
        )
        self.assertTrue(
            session.post.call_args.kwargs["data"].startswith(public_rooms.DIRECTORY_PREFIX)
        )

    def test_lease_stops_with_participant(self):
        stop = threading.Event()
        session = Mock()
        session.post.return_value = FakeResponse()
        room = public_rooms.create_room("Design")
        stop.set()
        public_rooms.maintain_lease(room, "https://relay", stop, session)
        session.post.assert_not_called()

    def test_default_transport_reuses_tor_aware_network_session(self):
        from enchat_lib import network

        self.assertIs(network.session, public_rooms._transport())

    def test_directory_failure_is_distinct_from_empty_directory(self):
        session = Mock()
        session.get.side_effect = public_rooms.requests.ConnectionError("offline")
        with self.assertRaises(public_rooms.DirectoryUnavailable):
            public_rooms.list_active_rooms("https://relay", session=session)


if __name__ == "__main__":
    unittest.main()
