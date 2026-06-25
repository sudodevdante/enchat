import os
import tempfile

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

CONF_FILE = os.path.expanduser("~/.enchat.conf")
DEFAULT_NTFY = "https://ntfy.sh"
ENCHAT_NTFY = "https://enchat.salvc.com"
LEGACY_ENCHAT_NTFY = "https://enchat.sudosallie.com"
MAX_MSG_LEN = 500
PING_INTERVAL = 25
MAX_RETRIES = 3
RETRY_BASE = 1
MAX_SEEN = 2000
BUFFER_LIMIT = 500
TRIM_STEP = 100

MAX_FILE_SIZE = 5 * 1024 * 1024
CHUNK_SIZE = 6 * 1024
FILE_TEMP_DIR = os.path.join(tempfile.gettempdir(), "enchat_files")
# The 'downloads' directory should be at the project root, next to enchat.py
# and the enchat_lib directory.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADS_DIR = os.path.join(_project_root, "downloads")
VERSION = "2.3.0"

KEYRING_SERVICE_NAME = "enchat"

USER_TIMEOUT = 60 # seconds. Must be > PING_INTERVAL
AUTO_CLEANUP_DELAY = 30 # seconds. Delay before auto-cleanup when room becomes empty
