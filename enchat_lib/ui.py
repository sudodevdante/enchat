"""Textual user interface for Enchat.

The UI deliberately sits on top of the existing network and command modules. This
keeps transport and encryption behaviour unchanged while giving the chat a
responsive, keyboard-first interface.
"""

from __future__ import annotations

import threading
import time
import textwrap
from datetime import datetime
from typing import List, Optional

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.suggester import SuggestFromList
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from . import commands, constants, network, state


COMMANDS = [
    "/help",
    "/who",
    "/share-room",
    "/copy-link",
    "/share ",
    "/files",
    "/download ",
    "/security",
    "/server",
    "/notifications",
    "/clear",
    "/exit",
]


class ActionPalette(ModalScreen[str]):
    """Small keyboard-first action launcher."""

    DEFAULT_CSS = """
    ActionPalette {
        align: center middle;
        background: #02090f 70%;
    }

    #palette {
        width: 58;
        height: auto;
        max-height: 20;
        padding: 1 2;
        background: #071521;
        border: solid #405568;
    }

    #palette-title {
        height: 2;
        color: #54dff4;
        text-style: bold;
    }

    #palette-options {
        height: auto;
        max-height: 14;
        background: #071521;
        border: none;
    }

    #palette-options > .option-list--option-highlighted {
        background: #54dff4;
        color: #03101a;
        text-style: bold;
    }
    """

    BINDINGS = [Binding("escape", "dismiss_palette", "Close", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="palette"):
            yield Static("Actions", id="palette-title")
            yield OptionList(
                Option("Invite people", id="invite"),
                Option("Share a file", id="share"),
                Option("View members", id="members"),
                Option("Security details", id="security"),
                Option("Help and shortcuts", id="help"),
                id="palette-options",
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def choose_action(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))

    def action_dismiss_palette(self) -> None:
        self.dismiss("")


class EnchatApp(App[None]):
    """Responsive chat application backed by an existing :class:`ChatUI`."""

    TITLE = "Enchat"
    CSS = """
    $base: #050f18;
    $surface: #071521;
    $line: #263a4b;
    $muted: #8292a8;
    $text: #f2eee7;
    $cyan: #54dff4;
    $green: #62e889;

    Screen {
        background: $base;
        color: $text;
        layout: vertical;
    }

    #topbar {
        height: 3;
        padding: 1 2 0 2;
        border-bottom: solid $line;
        background: $base;
    }

    #main {
        height: 1fr;
        background: $base;
    }

    #conversation {
        width: 1fr;
        height: 1fr;
        background: $base;
        padding: 1 2 0 2;
        scrollbar-color: #405568;
        scrollbar-background: $base;
        scrollbar-size: 1 1;
    }

    #members {
        width: 31;
        min-width: 25;
        height: 1fr;
        padding: 1 2;
        border-left: solid $line;
        background: $base;
        color: $text;
    }

    #members.hidden {
        display: none;
    }

    #composer-wrap {
        height: 5;
        padding: 0 2;
        background: $base;
    }

    #composer {
        height: 3;
        padding: 0 1;
        background: $base;
        border: solid #405568;
        color: $text;
    }

    #composer:focus {
        border: solid $cyan;
    }

    #shortcuts {
        height: 2;
        padding: 0 2;
        color: $muted;
        background: $base;
        border-top: solid $line;
    }

    .shortcut {
        color: $cyan;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("ctrl+k", "open_actions", "Actions", show=False, priority=True),
        Binding("ctrl+m", "toggle_members", "Members", show=False, priority=True),
        Binding("f1", "show_help", "Help", show=False, priority=True),
        Binding("ctrl+q", "leave", "Leave", show=False, priority=True),
    ]

    def __init__(self, chat: "ChatUI", network_enabled: bool = True) -> None:
        super().__init__()
        self.chat = chat
        self.network_enabled = network_enabled
        self._rendered_count = 0
        self._message_times: List[str] = []
        self._members_requested = True
        self._presence_signature = None
        self._status_signature = None
        self._stop_evt = threading.Event()
        self._chat_screen: Optional[Screen] = None

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="topbar")
        with Horizontal(id="main"):
            yield RichLog(id="conversation", markup=True, wrap=True, auto_scroll=True)
            yield Static(id="members")
        with Vertical(id="composer-wrap"):
            yield Input(
                placeholder=f"Message #{self.chat.room_label}",
                id="composer",
                max_length=constants.MAX_MSG_LEN,
                suggester=SuggestFromList(COMMANDS, case_sensitive=False),
            )
        yield Static(self._shortcut_text(), id="shortcuts")

    def on_mount(self) -> None:
        self._chat_screen = self.screen
        state.room_participants[self.chat.nick] = time.time()
        self._query_chat("#composer", Input).focus()
        # Poll only the shared message buffer at a low cost. Presence has its own
        # slower timer and only redraws when the participant set changes.
        self.set_interval(0.10, self._sync_view)
        self.set_interval(1.0, self._sync_presence)
        self.set_interval(0.5, self._sync_status)

        if self.network_enabled:
            threading.Thread(
                target=network.listener,
                args=(
                    self.chat.room,
                    self.chat.nick,
                    self.chat.fernet,
                    self.chat.server,
                    self.chat.buf,
                    self._stop_evt,
                    self.chat.shutdown_event,
                ),
                daemon=True,
            ).start()
            threading.Thread(target=self.chat._reaper, args=(self._stop_evt,), daemon=True).start()
            threading.Thread(target=self._pinger, daemon=True).start()
            self.chat.buf.append(("System", f"Joined '{self.chat.room_label}'", False))
            network.enqueue_sys(
                self.chat.room, self.chat.nick, "joined", self.chat.server, self.chat.fernet
            )

        self._sync_view()
        self._sync_presence(force=True)
        self._sync_status(force=True)

    def on_unmount(self) -> None:
        self._stop_evt.set()

    def _pinger(self) -> None:
        while not self._stop_evt.is_set() and not self.chat.shutdown_event.is_set():
            network.enqueue_sys(
                self.chat.room, self.chat.nick, "ping", self.chat.server, self.chat.fernet
            )
            self._stop_evt.wait(constants.PING_INTERVAL)

    def _header_text(self) -> Text:
        text = Text()
        text.append("ENCHAT", style="bold #54dff4")
        text.append(f"   │   #{self.chat.room_label}", style="bold #f2eee7")
        text.append("   │   encrypted", style="#62e889")
        if self.chat.is_tor:
            text.append("   │   TOR", style="bold #c59cff")
        status = state.relay_status
        status_style = {
            "connected": "#62e889",
            "connecting": "#f2c14e",
            "offline": "bold #ff6b6b",
        }.get(status, "#8292a8")
        text.append(f"   │   {status}", style=status_style)
        return text

    @staticmethod
    def _shortcut_text() -> Text:
        text = Text()
        for key, label in (
            ("Ctrl+K", "actions"),
            ("Ctrl+M", "members"),
            ("/", "commands"),
            ("F1", "help"),
        ):
            if text:
                text.append("     ")
            text.append(key, style="bold #54dff4")
            text.append(f" {label}", style="#8292a8")
        return text

    def _sync_view(self) -> None:
        if self.chat.shutdown_event.is_set():
            self.exit()
            return

        try:
            log = self._query_chat("#conversation", RichLog)
        except NoMatches:
            # The periodic refresh can race with screen teardown in Textual.
            return
        if len(self.chat.buf) < self._rendered_count:
            log.clear()
            self._rendered_count = 0
            self._message_times.clear()

        while self._rendered_count < len(self.chat.buf):
            entry = self.chat.buf[self._rendered_count]
            self._message_times.append(datetime.now().strftime("%H:%M"))
            log.write(self._render_message(entry, self._message_times[-1]))
            if entry[0] != "System":
                log.write(Text(""))
            self._rendered_count += 1

    def _active_participant_names(self) -> tuple:
        now = time.time()
        names = {
            name
            for name, seen in state.room_participants.items()
            if now - seen <= constants.USER_TIMEOUT
        }
        names.add(self.chat.nick)
        return tuple(sorted(names, key=lambda value: (value == self.chat.nick, value.lower())))

    def _sync_presence(self, force: bool = False) -> None:
        signature = self._active_participant_names()
        if not force and signature == self._presence_signature:
            return
        self._presence_signature = signature
        try:
            self._query_chat("#members", Static).update(self._members_text(signature))
        except NoMatches:
            return

    def _sync_status(self, force: bool = False) -> None:
        signature = (state.relay_status, state.relay_error)
        if not force and signature == self._status_signature:
            return
        self._status_signature = signature
        try:
            self._query_chat("#topbar", Static).update(self._header_text())
        except NoMatches:
            return

    def _query_chat(self, selector: str, widget_type):
        """Query the base chat screen even while a modal is open."""
        screen = self._chat_screen or self.screen
        return screen.query_one(selector, widget_type)

    def _render_message(self, entry: tuple, stamp: str):
        sender, content, own = entry[0], entry[1], bool(entry[2])
        if isinstance(content, Panel):
            return content

        if sender == "System":
            line = Text(f"{stamp}    →  ", style="#8292a8")
            if isinstance(content, Text):
                line.append_text(content)
            else:
                line.append(Text.from_markup(str(content), style="#8292a8"))
            return line

        label = "You" if own else sender
        line = Text(f"{stamp}    ", style="#8292a8")
        line.append(label, style="bold #54dff4")
        line.append("\n         ")
        if isinstance(content, Text):
            line.append_text(content)
        else:
            wrapped = textwrap.fill(
                str(content),
                width=64,
                subsequent_indent="         ",
                break_long_words=False,
                break_on_hyphens=False,
            )
            line.append(wrapped, style="#f2eee7")
        line.append("\n\n")
        return line

    def _members_text(self, names: Optional[tuple] = None) -> Group:
        names = names or self._active_participant_names()
        rows = [Text(f"Participants ({len(names)})", style="bold #54dff4"), Text("")]
        for name in names:
            label = "You" if name == self.chat.nick else name
            row = Text()
            row.append(label, style="bold #54dff4")
            row.append("  •", style="#62e889")
            row.append(" online", style="#66788d")
            rows.append(row)
            rows.append(Text(""))
        return Group(*rows)

    @on(Input.Submitted, "#composer")
    def submit_message(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.value = ""
        if not value:
            return
        self._handle_line(value)

    def _handle_line(self, line: str) -> None:
        if line.startswith("/"):
            result = commands.handle_command(
                line,
                self.chat.room,
                self.chat.nick,
                self.chat.server,
                self.chat.fernet,
                self.chat.buf,
                self.chat.secret,
                self.chat.is_public,
                self.chat.is_tor,
            )
            if result == "exit":
                self.action_leave()
        else:
            if self.network_enabled:
                network.enqueue_msg(
                    self.chat.room,
                    self.chat.nick,
                    line,
                    self.chat.server,
                    self.chat.fernet,
                )
            self.chat.buf.append((self.chat.nick, line, True, False))
        self._sync_view()

    def action_open_actions(self) -> None:
        self.push_screen(ActionPalette(), self._run_palette_action)

    def _run_palette_action(self, action: Optional[str]) -> None:
        if action == "invite":
            self._handle_line("/share-room")
        elif action == "share":
            composer = self._query_chat("#composer", Input)
            composer.value = "/share "
            composer.cursor_position = len(composer.value)
            composer.focus()
        elif action == "members":
            self.action_toggle_members()
        elif action == "security":
            self._handle_line("/security")
        elif action == "help":
            self._handle_line("/help")

    def action_toggle_members(self) -> None:
        self._members_requested = not self._members_requested
        self._apply_members_visibility()

    def action_show_help(self) -> None:
        self._handle_line("/help")

    def action_leave(self) -> None:
        self.chat.shutdown_event.set()
        self.exit()

    def _apply_members_visibility(self) -> None:
        members = self._query_chat("#members", Static)
        should_show = self._members_requested and self.size.width >= 105
        members.set_class(not should_show, "hidden")

    def on_resize(self, event: events.Resize) -> None:
        self._apply_members_visibility()


class ChatUI:
    """Compatibility wrapper used by the existing Enchat entry point."""

    def __init__(
        self,
        room,
        nick,
        server,
        f,
        buf,
        secret,
        is_public=False,
        is_tor=False,
        shutdown_event=None,
        room_label=None,
    ):
        self.room = room
        self.room_label = room_label or room
        self.nick = nick
        self.server = server
        self.fernet = f
        self.buf = buf
        self.secret = secret
        self.is_public = is_public
        self.is_tor = is_tor
        self.shutdown_event = shutdown_event or threading.Event()

    def _reaper(self, stop_evt: threading.Event) -> None:
        while not stop_evt.wait(constants.PING_INTERVAL):
            now = time.time()
            for user, last_seen in list(state.room_participants.items()):
                if user == self.nick:
                    continue
                if now - last_seen > constants.USER_TIMEOUT:
                    state.room_participants.pop(user, None)
                    self.buf.append(
                        ("System", Text(f"{user} left (timed out)", style="dim"), False)
                    )

    def run(self) -> None:
        EnchatApp(self).run()


def build_preview_app() -> EnchatApp:
    """Create a deterministic offline app for visual QA and tests."""
    from cryptography.fernet import Fernet

    now = time.time()
    state.room_participants.clear()
    state.room_participants.update({"Maya": now, "Noor": now, "you": now})
    state.relay_status = "connected"
    state.relay_error = ""
    preview = [
        ("you", "Pushed the fixes for the import flow. Can you pull and give it a try?", True),
        ("Maya", "On it. I’ll run through a few edge cases and report back.", False),
        ("Noor", "I added a short note in docs/usage.md about the new flags.", False),
        ("System", "Maya joined #studio", False),
        ("Maya", "Looks good overall. One small nit on the error text.", False),
        ("you", "Sounds like a plan. Appreciate it, team.", True),
    ]
    chat = ChatUI(
        "studio",
        "you",
        "https://relay.example",
        Fernet(Fernet.generate_key()),
        preview,
        "preview-only",
    )
    return EnchatApp(chat, network_enabled=False)
