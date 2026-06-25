"""Keyboard-first Textual onboarding for Enchat."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Collapsible, Input, Label, Select, Static

from . import constants, link_sharing, public_rooms


@dataclass
class OnboardingResult:
    action: str
    room: str = ""
    nick: str = ""
    secret: str = ""
    server: str = constants.ENCHAT_NTFY
    link: str = ""
    public_room: str = ""
    public_room_id: str = ""
    remember: bool = True
    save_secret: bool = True


class OnboardingScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", show=False)]

    def action_back(self) -> None:
        if len(self.app.screen_stack) > 2:
            self.app.pop_screen()
        else:
            self.app.exit(None)


class WelcomeScreen(OnboardingScreen):
    BINDINGS = OnboardingScreen.BINDINGS + [
        Binding("up", "previous_action", "Previous", show=False, priority=True),
        Binding("down", "next_action", "Next", show=False, priority=True),
    ]

    def __init__(
        self,
        saved_room: str = "",
        saved_nick: str = "",
        public_server: str = constants.ENCHAT_NTFY,
    ) -> None:
        super().__init__()
        self.saved_room = saved_room
        self.saved_nick = saved_nick
        self.public_server = public_server

    def compose(self) -> ComposeResult:
        with Vertical(classes="welcome-card"):
            yield Static("ENCHAT", classes="brand")
            yield Static(f"v{constants.VERSION}  ·  encrypted terminal chat", classes="subtitle")
            yield Static("What would you like to do?", classes="section-title")
            if self.saved_room:
                yield Button(
                    f"Continue  #{self.saved_room}  as {self.saved_nick}",
                    id="continue-room",
                    variant="primary",
                    classes="menu-action",
                )
            yield Button("Create private room", id="create-private", classes="menu-action")
            yield Button("Join private room", id="join-private", classes="menu-action")
            yield Button("Join with invite link", id="join-link", classes="menu-action")
            yield Button("Public rooms", id="public-rooms", classes="menu-action")
            yield Static("↑↓ navigate   Enter select   Esc quit", classes="hint")

    def on_mount(self) -> None:
        first = self.query("Button").first()
        if first:
            first.focus()

    def action_previous_action(self) -> None:
        self.focus_previous()

    def action_next_action(self) -> None:
        self.focus_next()

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        if event.button.id == "continue-room":
            self.app.exit(OnboardingResult(action="continue"))
        elif event.button.id == "create-private":
            self.app.push_screen(RoomFormScreen("create"))
        elif event.button.id == "join-private":
            self.app.push_screen(RoomFormScreen("join"))
        elif event.button.id == "join-link":
            self.app.push_screen(InviteFormScreen())
        elif event.button.id == "public-rooms":
            self.app.push_screen(PublicRoomScreen(self.saved_nick, self.public_server))


class ServerFields:
    def server_widgets(self):
        yield Collapsible(
            Label("Relay", classes="field-label"),
            Select(
                [
                    ("Enchat relay · recommended", constants.ENCHAT_NTFY),
                    ("Public ntfy.sh", constants.DEFAULT_NTFY),
                    ("Custom URL", "custom"),
                ],
                value=constants.ENCHAT_NTFY,
                allow_blank=False,
                id="server-choice",
            ),
            Input(
                placeholder="https://relay.example.com",
                id="custom-server",
                classes="hidden",
            ),
            title="Advanced",
            collapsed=True,
            id="advanced",
        )

    def selected_server(self) -> str:
        value = self.query_one("#server-choice", Select).value
        if value == "custom":
            return self.query_one("#custom-server", Input).value.strip().rstrip("/")
        return str(value).rstrip("/")


class RoomFormScreen(OnboardingScreen, ServerFields):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode

    def compose(self) -> ComposeResult:
        title = "Create private room" if self.mode == "create" else "Join private room"
        description = (
            "A strong room key will be generated for you."
            if self.mode == "create"
            else "Enter the exact room name and passphrase shared with you."
        )
        with Vertical(classes="form-card"):
            yield Static(title, classes="form-title")
            yield Static(description, classes="subtitle")
            yield Label("Room name", classes="field-label")
            yield Input(placeholder="studio", id="room", max_length=80)
            yield Label("Nickname", classes="field-label")
            yield Input(placeholder="How others see you", id="nick", max_length=40)
            if self.mode == "join":
                yield Label("Passphrase", classes="field-label")
                yield Input(placeholder="Hidden", password=True, id="secret")
            yield from self.server_widgets()
            with Horizontal(classes="save-options"):
                yield Checkbox("Remember room", value=True, id="remember")
                if self.mode == "join":
                    yield Checkbox("Store passphrase in keychain", value=True, id="save-secret")
            yield Static("", id="form-error", classes="error")
            with Horizontal(classes="form-actions"):
                yield Button("Back", id="back")
                yield Button(
                    "Create room" if self.mode == "create" else "Join room",
                    id="submit",
                    variant="primary",
                )
            yield Static("Tab next   Enter continue   Esc back", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#room", Input).focus()

    @on(Select.Changed, "#server-choice")
    def server_changed(self, event: Select.Changed) -> None:
        custom = self.query_one("#custom-server", Input)
        custom.set_class(event.value != "custom", "hidden")

    @on(Button.Pressed, "#back")
    def go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        room = self.query_one("#room", Input).value.strip()
        nick = self.query_one("#nick", Input).value.strip()
        secret = self.query_one("#secret", Input).value if self.mode == "join" else ""
        server = self.selected_server()
        error = self.query_one("#form-error", Static)
        if not room or not nick:
            error.update("Room name and nickname are required.")
            return
        if self.mode == "join" and not secret:
            error.update("Passphrase is required.")
            return
        if not server.startswith(("https://", "http://")):
            error.update("Relay must be a valid http(s) URL.")
            return
        self.app.exit(
            OnboardingResult(
                action=self.mode,
                room=room,
                nick=nick,
                secret=secret,
                server=server,
                remember=self.query_one("#remember", Checkbox).value,
                save_secret=(
                    self.query_one("#save-secret", Checkbox).value
                    if self.mode == "join"
                    else True
                ),
            )
        )

    @on(Input.Submitted)
    def submit_from_input(self) -> None:
        self.submit()


class InviteFormScreen(OnboardingScreen):
    def compose(self) -> ComposeResult:
        with Vertical(classes="form-card"):
            yield Static("Join with invite link", classes="form-title")
            yield Static("Paste the complete one-time Enchat invitation.", classes="subtitle")
            yield Label("Invite link", classes="field-label")
            yield Input(placeholder="https://share.enchat.io/join#…", id="link")
            yield Label("Nickname", classes="field-label")
            yield Input(placeholder="How others see you", id="nick", max_length=40)
            yield Checkbox("Remember this room after joining", value=False, id="remember")
            yield Static("", id="form-error", classes="error")
            with Horizontal(classes="form-actions"):
                yield Button("Back", id="back")
                yield Button("Use invite", id="submit", variant="primary")
            yield Static("Tab next   Enter continue   Esc back", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#link", Input).focus()

    @on(Button.Pressed, "#back")
    def go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        link = self.query_one("#link", Input).value.strip()
        nick = self.query_one("#nick", Input).value.strip()
        error = self.query_one("#form-error", Static)
        if not link_sharing.parse_share_url(link):
            error.update("This is not a valid Enchat invite link.")
            return
        if not nick:
            error.update("Nickname is required.")
            return
        self.app.exit(
            OnboardingResult(
                action="invite",
                link=link,
                nick=nick,
                remember=self.query_one("#remember", Checkbox).value,
            )
        )

    @on(Input.Submitted)
    def submit_from_input(self) -> None:
        self.submit()


class PublicRoomScreen(OnboardingScreen):
    def __init__(
        self,
        saved_nick: str = "",
        server: str = constants.ENCHAT_NTFY,
    ) -> None:
        super().__init__()
        self.saved_nick = saved_nick
        self.server = server
        self.rooms: dict[str, public_rooms.PublicRoom] = {}
        self._refresh_number = 0

    def compose(self) -> ComposeResult:
        with Vertical(classes="form-card"):
            yield Static("Public rooms", classes="form-title")
            yield Static(
                "Rooms stay listed while at least one participant remains active.",
                classes="subtitle",
            )
            yield Label("Active rooms", classes="field-label")
            yield Select(
                [],
                prompt="Looking for active rooms…",
                allow_blank=True,
                id="public-room",
            )
            yield Static("Connecting to the public directory…", id="directory-status")
            yield Label("Nickname", classes="field-label")
            yield Input(
                value=self.saved_nick,
                placeholder="How others see you",
                id="nick",
                max_length=40,
            )
            yield Static("", id="form-error", classes="error")
            with Horizontal(classes="form-actions public-actions"):
                yield Button("Back", id="back")
                yield Button("Refresh", id="refresh")
                yield Button("Create", id="create")
                yield Button("Join", id="submit", variant="primary")
            yield Static("Tab next   Enter continue   Esc back", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#nick", Input).focus()
        self.refresh_rooms()

    def refresh_rooms(self) -> None:
        self._refresh_number += 1
        refresh_number = self._refresh_number
        self.query_one("#directory-status", Static).update("Refreshing active rooms…")
        threading.Thread(
            target=self._load_rooms,
            args=(refresh_number,),
            daemon=True,
        ).start()

    def _load_rooms(self, refresh_number: int) -> None:
        try:
            rooms = public_rooms.list_active_rooms(self.server)
        except public_rooms.DirectoryUnavailable:
            try:
                self.app.call_from_thread(self._show_directory_error, refresh_number)
            except RuntimeError:
                return
            return
        try:
            self.app.call_from_thread(self._show_rooms, refresh_number, rooms)
        except RuntimeError:
            # The user may leave the screen while the request is in flight.
            return

    def _show_rooms(
        self, refresh_number: int, rooms: list[public_rooms.PublicRoom]
    ) -> None:
        if refresh_number != self._refresh_number:
            return
        self.rooms = {room.room_id: room for room in rooms}
        select = self.query_one("#public-room", Select)
        select.set_options([(f"{room.name}", room.room_id) for room in rooms])
        status = self.query_one("#directory-status", Static)
        if rooms:
            select.value = rooms[0].room_id
            status.update(f"{len(rooms)} active room{'s' if len(rooms) != 1 else ''}")
        else:
            select.value = Select.BLANK
            status.update("No active rooms yet — create the first one.")

    def _show_directory_error(self, refresh_number: int) -> None:
        if refresh_number != self._refresh_number:
            return
        self.query_one("#directory-status", Static).update(
            "Directory unavailable — check the relay and try Refresh."
        )

    @on(Button.Pressed, "#back")
    def go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#refresh")
    def refresh_pressed(self) -> None:
        self.refresh_rooms()

    @on(Button.Pressed, "#create")
    def create_pressed(self) -> None:
        self.app.push_screen(
            PublicRoomCreateScreen(
                self.query_one("#nick", Input).value.strip(), self.server
            )
        )

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        nick = self.query_one("#nick", Input).value.strip()
        if not nick:
            self.query_one("#form-error", Static).update("Nickname is required.")
            return
        selected = self.query_one("#public-room", Select).value
        room = self.rooms.get(str(selected))
        if room is None:
            self.query_one("#form-error", Static).update(
                "Select an active room or create a new one."
            )
            return
        self.app.exit(
            OnboardingResult(
                action="public",
                room=room.topic,
                secret=room.secret,
                public_room=room.name,
                public_room_id=room.room_id,
                nick=nick,
                server=self.server,
            )
        )

    @on(Input.Submitted)
    def submit_from_input(self) -> None:
        self.submit()


class PublicRoomCreateScreen(OnboardingScreen):
    def __init__(
        self,
        saved_nick: str = "",
        server: str = constants.ENCHAT_NTFY,
    ) -> None:
        super().__init__()
        self.saved_nick = saved_nick
        self.server = server

    def compose(self) -> ComposeResult:
        with Vertical(classes="form-card"):
            yield Static("Create public room", classes="form-title")
            yield Static(
                "Anyone can discover and join it while the room remains active.",
                classes="subtitle",
            )
            yield Label("Room name", classes="field-label")
            yield Input(placeholder="Coffee break", id="room", max_length=48)
            yield Label("Nickname", classes="field-label")
            yield Input(
                value=self.saved_nick,
                placeholder="How others see you",
                id="nick",
                max_length=40,
            )
            yield Static("", id="form-error", classes="error")
            with Horizontal(classes="form-actions"):
                yield Button("Back", id="back")
                yield Button("Create and join", id="submit", variant="primary")
            yield Static("Tab next   Enter create   Esc back", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#room", Input).focus()

    @on(Button.Pressed, "#back")
    def go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        name = self.query_one("#room", Input).value.strip()
        nick = self.query_one("#nick", Input).value.strip()
        error = self.query_one("#form-error", Static)
        if not name or not nick:
            error.update("Room name and nickname are required.")
            return
        try:
            room = public_rooms.create_room(name)
        except ValueError as exc:
            error.update(str(exc))
            return
        self.app.exit(
            OnboardingResult(
                action="public",
                room=room.topic,
                secret=room.secret,
                public_room=room.name,
                public_room_id=room.room_id,
                nick=nick,
                server=self.server,
            )
        )

    @on(Input.Submitted)
    def submit_from_input(self) -> None:
        self.submit()


class OnboardingApp(App[Optional[OnboardingResult]]):
    TITLE = "Enchat"
    CSS = """
    Screen {
        align: center middle;
        background: #050f18;
        color: #f2eee7;
    }

    .welcome-card, .form-card {
        width: 76;
        max-width: 94%;
        height: auto;
        max-height: 95%;
        padding: 1 4;
        background: #071521;
        border: solid #263a4b;
    }

    .brand {
        height: 2;
        color: #54dff4;
        text-style: bold;
        text-align: center;
    }

    .subtitle {
        height: auto;
        min-height: 2;
        color: #8292a8;
        text-align: center;
        margin-bottom: 1;
    }

    .section-title, .form-title {
        height: 2;
        color: #f2eee7;
        text-style: bold;
    }

    .form-title {
        color: #54dff4;
        text-align: center;
    }

    .menu-action {
        width: 100%;
        margin-bottom: 1;
        background: #071521;
        color: #f2eee7;
        border: solid #405568;
    }

    .menu-action:focus {
        background: #123044;
        border: solid #54dff4;
        color: #ffffff;
    }

    .field-label {
        height: 1;
        margin-top: 1;
        color: #8292a8;
    }

    Input, Select {
        width: 100%;
        background: #050f18;
        color: #f2eee7;
        border: solid #405568;
    }

    Input:focus, Select:focus {
        border: solid #54dff4;
    }

    Checkbox {
        height: 3;
        margin-top: 1;
        color: #8292a8;
    }

    .save-options {
        height: 3;
        margin-top: 1;
    }

    .save-options Checkbox {
        width: auto;
        margin: 0 2 0 0;
    }

    Collapsible {
        margin-top: 1;
        padding: 0;
        border: none;
        background: #071521;
    }

    CollapsibleTitle {
        color: #8292a8;
    }

    .form-actions {
        height: 3;
        margin-top: 1;
        align-horizontal: right;
    }

    .form-actions Button {
        min-width: 16;
        margin-left: 1;
    }

    .public-actions Button {
        width: 1fr;
        min-width: 8;
    }

    .error {
        height: auto;
        min-height: 1;
        color: #ff6b6b;
        margin-top: 1;
    }

    .hint {
        height: 2;
        margin-top: 1;
        color: #66788d;
        text-align: center;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(
        self,
        saved_room: str = "",
        saved_nick: str = "",
        public_server: str = constants.ENCHAT_NTFY,
    ) -> None:
        super().__init__()
        self.saved_room = saved_room
        self.saved_nick = saved_nick
        self.public_server = public_server

    def on_mount(self) -> None:
        self.push_screen(
            WelcomeScreen(self.saved_room, self.saved_nick, self.public_server)
        )


def run_onboarding(
    saved_room: str = "",
    saved_nick: str = "",
    public_server: str = constants.ENCHAT_NTFY,
) -> Optional[OnboardingResult]:
    return OnboardingApp(saved_room, saved_nick, public_server).run()
