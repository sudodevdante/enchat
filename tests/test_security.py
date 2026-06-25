import os
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from enchat_lib import config, file_transfer, notifications, state


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self):
        state.available_files.clear()
        state.file_chunks.clear()

    def test_config_never_writes_plaintext_passphrase(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config")
            with patch.object(config, "CONF_FILE", path):
                config.save_conf("studio", "Alice", "do-not-store", "https://relay")
            with open(path, encoding="utf-8") as saved:
                self.assertNotIn("do-not-store", saved.read())

    def test_malicious_file_metadata_is_ignored(self):
        metadata = {
            "file_id": "../escape",
            "filename": "../../outside.txt",
            "size": 1,
            "total_chunks": 999999,
            "hash": "0" * 64,
        }
        file_transfer.handle_file_metadata(metadata, "Mallory", [])
        self.assertEqual({}, state.available_files)

    def test_received_filename_cannot_escape_temp_directory(self):
        cipher = Fernet(Fernet.generate_key())
        data = b"safe"
        file_id = "deadbeef"
        import hashlib
        token = cipher.encrypt(data).decode()
        state.available_files[file_id] = {
            "complete": True,
            "metadata": {
                "file_id": file_id,
                "filename": "../../outside.txt",
                "size": len(data),
                "total_chunks": 1,
                "hash": hashlib.sha256(data).hexdigest(),
            },
        }
        state.file_chunks[file_id] = {0: {"data": token}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            file_transfer.constants, "FILE_TEMP_DIR", directory
        ):
            path, error = file_transfer.assemble_file_from_chunks(file_id, cipher)
            self.assertIsNone(error)
            self.assertEqual(directory, os.path.dirname(path))

    @patch("enchat_lib.notifications.subprocess.run")
    def test_macos_notification_passes_message_as_argument(self, run):
        message = 'hello" & do shell script "bad"'
        notifications._notify_macos(message)
        argv = run.call_args.args[0]
        self.assertEqual(message, argv[-1])
        self.assertNotIn(message, " ".join(argv[:-1]))


if __name__ == "__main__":
    unittest.main()
