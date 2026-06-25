import unittest
import queue
import threading
from unittest.mock import patch

from cryptography.fernet import Fernet

from enchat_lib import crypto, network, session_key, state


class AtomicWireProtocolTests(unittest.TestCase):
    def setUp(self):
        session_key._active_sessions.clear()
        self.key = Fernet.generate_key()
        self.sender = Fernet(self.key)
        self.receiver = Fernet(self.key)

    def test_two_independent_clients_decode_same_room_message(self):
        token = network.encode_wire_message("Alice", "hello|with a pipe", self.sender, 123)
        self.assertEqual(
            ("123", "Alice", "hello|with a pipe"),
            network.decode_wire_message(token, self.receiver, "studio"),
        )

    def test_v2_does_not_require_a_session_key(self):
        token = network.encode_wire_message("Bob", "joined", self.sender, 456)
        self.assertIsNone(session_key.get_session_key("studio"))
        self.assertEqual(
            ("456", "Bob", "joined"),
            network.decode_wire_message(token, self.receiver, "studio"),
        )

    def test_wrong_room_key_cannot_decode(self):
        token = network.encode_wire_message("Alice", "secret", self.sender, 789)
        self.assertIsNone(
            network.decode_wire_message(token, Fernet(Fernet.generate_key()), "studio")
        )

    def test_ntfy_json_message_event_is_parsed(self):
        raw = '{"id":"abc123","event":"message","message":"MSG:token"}'
        self.assertEqual(("abc123", "MSG:token"), network.parse_subscription_event(raw))

    def test_ntfy_keepalive_is_ignored(self):
        raw = '{"id":"abc123","event":"keepalive"}'
        self.assertIsNone(network.parse_subscription_event(raw))

    def test_new_subscription_does_not_request_cached_history(self):
        self.assertEqual(
            "https://enchat.salvc.com/studio/json",
            network.subscription_url("https://enchat.salvc.com", "studio"),
        )

    def test_reconnect_resumes_after_last_event(self):
        self.assertEqual(
            "https://enchat.salvc.com/studio/json?since=abc123",
            network.subscription_url(
                "https://enchat.salvc.com/", "studio", "abc123"
            ),
        )

    def test_retired_relay_migrates_to_default(self):
        self.assertEqual(
            "https://enchat.salvc.com",
            network.resolve_server("https://enchat.sudosallie.com/"),
        )

    def test_current_enchat_relay_is_preserved(self):
        self.assertEqual(
            "https://enchat.salvc.com",
            network.resolve_server("https://enchat.salvc.com/"),
        )

    def test_legacy_message_is_still_readable_with_legacy_key(self):
        legacy_key = Fernet.generate_key()
        session_key.set_session_key("studio", legacy_key)
        inner = session_key.encrypt_with_session("321|Legacy|hello", legacy_key)
        token = crypto.encrypt(inner, self.sender)
        self.assertEqual(
            ("321", "Legacy", "hello"),
            network.decode_wire_message(token, self.receiver, "studio"),
        )

    def test_outbox_sends_one_atomic_event_without_session_key_event(self):
        class Response:
            status_code = 200
            headers = {}

        stop = threading.Event()
        with patch.object(network.session, "post", return_value=Response()) as post:
            worker = threading.Thread(target=network.outbox_worker, args=(stop,), daemon=True)
            worker.start()
            state.outbox_queue.put(
                ("SYS", "studio", "Alice", "joined", "https://relay.example", self.sender)
            )
            state.outbox_queue.join()
            stop.set()
            worker.join(timeout=1)

        bodies = [call.kwargs["data"] for call in post.call_args_list]
        self.assertEqual(1, len(bodies))
        self.assertTrue(bodies[0].startswith("SYS:"))
        self.assertFalse(any(body.startswith("SESSIONKEY:") for body in bodies))
        token = bodies[0].partition(":")[2]
        decoded = network.decode_wire_message(token, self.receiver, "studio")
        self.assertIsNotNone(decoded)
        self.assertEqual(("Alice", "SYSTEM:joined"), decoded[1:])

    def test_outbox_wait_has_a_deadline(self):
        outbox = queue.Queue()
        outbox.put("pending")
        self.assertFalse(network.wait_for_outbox(outbox, timeout=0.01))
        outbox.get_nowait()
        outbox.task_done()
        self.assertTrue(network.wait_for_outbox(outbox, timeout=0.01))


if __name__ == "__main__":
    unittest.main()
