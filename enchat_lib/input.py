import os
import sys
import threading
import time

from . import state

def _posix():
    """POSIX implementation for non-blocking character input."""
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            # Check if there is data to be read on stdin
            import select
            if select.select([sys.stdin], [], [], 0.1)[0]:  # Increased timeout
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    state.input_queue.put("".join(state.current_input))
                    state.current_input.clear()
                elif ch == "\x03":  # Ctrl+C
                    state.input_queue.put("/exit")
                elif ch in ("\x7f", "\b") and state.current_input:  # Backspace
                    state.current_input.pop()
                else:
                    state.current_input.append(ch)
            else:
                # Slightly longer sleep to reduce CPU usage
                time.sleep(0.02)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _win():
    """Windows implementation for non-blocking character input."""
    import msvcrt
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                state.input_queue.put("".join(state.current_input))
                state.current_input.clear()
            elif ch == "\x03":  # Ctrl+C
                state.input_queue.put("/exit")
            elif ch == "\x08" and state.current_input:  # Backspace
                state.current_input.pop()
            else:
                state.current_input.append(ch)
        time.sleep(0.02)  # Reduced sleep for better responsiveness

def start_char_thread():
    """Starts the appropriate non-blocking input thread based on the OS."""
    thread = threading.Thread(target=_win if os.name == "nt" else _posix, daemon=True)
    thread.start()
