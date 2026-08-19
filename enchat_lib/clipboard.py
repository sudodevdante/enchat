"""
Cross-platform clipboard utility.
"""

def copy_to_clipboard(text: str) -> bool:
    """
    Copies the given text to the system clipboard.

    Returns True on success and False when the clipboard backend is missing
    or unavailable, so callers can fall back to displaying the text.
    """
    try:
        import pyperclip
    except ImportError:
        # pyperclip is not installed. The original code listed
        # ``pyperclip.PyperclipException`` in the same except clause, which
        # raised a NameError here because ``pyperclip`` is not bound on import
        # failure, crashing the /copy-link command.
        return False

    try:
        pyperclip.copy(text)
        return True
    except Exception:
        # No usable clipboard mechanism (headless Linux, missing xclip/xsel, etc.)
        return False