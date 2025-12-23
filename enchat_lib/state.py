import queue
from typing import Dict, List

# Shared application state
# This now stores the last seen time for each participant.
room_participants: Dict[str, float] = {}
notifications_enabled = True

# File transfer state
available_files: Dict[str, dict] = {}
file_chunks: Dict[str, dict] = {}  # Store chunks during transfer

# Queues for threads
outbox_queue: queue.Queue = queue.Queue()
input_queue: queue.Queue = queue.Queue()

# Non-blocking input buffer
current_input: List[str] = []

# Tor status
tor_ip = None

# In-memory state for lotteries, keyed by room name
# This is simple and resets if the client restarts.
lottery_state: Dict[str, dict] = {}

# In-memory state for polls, keyed by room name
poll_state: Dict[str, dict] = {}

# For link sharing
last_generated_link = ""
