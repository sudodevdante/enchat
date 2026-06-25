import unittest
from unittest.mock import patch

from textual.widgets import Button, Input, Select, Static

from enchat_lib import constants, public_rooms
from enchat_lib.onboarding import (
    OnboardingApp,
    OnboardingResult,
    PublicRoomCreateScreen,
    PublicRoomScreen,
    RoomFormScreen,
    WelcomeScreen,
)


class OnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_home_shows_saved_room_and_all_primary_actions(self):
        app = OnboardingApp("studio", "Wop")
        async with app.run_test(size=(100, 38)) as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, WelcomeScreen)
            labels = [button.label.plain for button in app.screen.query(Button)]
            self.assertIn("Continue  #studio  as Wop", labels)
            self.assertIn("Create private room", labels)
            self.assertIn("Join private room", labels)
            self.assertIn("Join with invite link", labels)
            self.assertIn("Public rooms", labels)

    async def test_arrow_keys_navigate_and_enter_selects(self):
        app = OnboardingApp("studio", "Wop")
        async with app.run_test(size=(100, 38)) as pilot:
            await pilot.pause()
            self.assertEqual("continue-room", app.focused.id)
            await pilot.press("down")
            self.assertEqual("create-private", app.focused.id)
            await pilot.press("down")
            self.assertEqual("join-private", app.focused.id)
            await pilot.press("up")
            self.assertEqual("create-private", app.focused.id)
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, RoomFormScreen)

    async def test_join_form_masks_passphrase_and_validates_required_fields(self):
        app = OnboardingApp()
        async with app.run_test(size=(100, 42)) as pilot:
            await pilot.pause()
            await pilot.click("#join-private")
            await pilot.pause()
            self.assertIsInstance(app.screen, RoomFormScreen)
            self.assertTrue(app.screen.query_one("#secret", Input).password)
            await pilot.click("#submit")
            await pilot.pause()
            error = app.screen.query_one("#form-error", Static).renderable
            self.assertIn("required", str(error))

    async def test_custom_relay_field_only_appears_for_custom_choice(self):
        app = OnboardingApp()
        async with app.run_test(size=(100, 42)) as pilot:
            await pilot.pause()
            await pilot.click("#join-private")
            await pilot.pause()
            custom = app.screen.query_one("#custom-server", Input)
            self.assertTrue(custom.has_class("hidden"))
            app.screen.query_one("#server-choice", Select).value = "custom"
            await pilot.pause()
            self.assertFalse(custom.has_class("hidden"))

    async def test_valid_join_returns_complete_profile(self):
        app = OnboardingApp()
        async with app.run_test(size=(100, 42)) as pilot:
            await pilot.pause()
            await pilot.click("#join-private")
            await pilot.pause()
            screen = app.screen
            screen.query_one("#room", Input).value = "studio"
            screen.query_one("#nick", Input).value = "Wop"
            screen.query_one("#secret", Input).value = "correct horse"
            with patch.object(app, "exit") as exit_app:
                screen.submit()
            result = exit_app.call_args.args[0]
            self.assertEqual(
                OnboardingResult(
                    action="join",
                    room="studio",
                    nick="Wop",
                    secret="correct horse",
                    server=constants.ENCHAT_NTFY,
                    remember=True,
                    save_secret=True,
                ),
                result,
            )

    async def test_active_public_room_can_be_selected_and_joined(self):
        room = public_rooms.PublicRoom(
            room_id="abcdefghijkl",
            name="Coffee break",
            topic="enchat-public-abcdefghijklmnopqrstuvwx",
            secret="a" * 43 + "=",
            expires_at=9999999999,
        )
        with patch.object(public_rooms, "list_active_rooms", return_value=[room]):
            app = OnboardingApp("", "Wop")
            async with app.run_test(size=(100, 42)) as pilot:
                await pilot.pause()
                await pilot.click("#public-rooms")
                await pilot.pause()
                self.assertIsInstance(app.screen, PublicRoomScreen)
                self.assertEqual(room.room_id, app.screen.query_one("#public-room", Select).value)
                with patch.object(app, "exit") as exit_app:
                    app.screen.submit()
                result = exit_app.call_args.args[0]
                self.assertEqual("public", result.action)
                self.assertEqual(room.topic, result.room)
                self.assertEqual("Coffee break", result.public_room)

    async def test_public_room_can_be_created_from_empty_directory(self):
        room = public_rooms.PublicRoom(
            room_id="abcdefghijkl",
            name="New room",
            topic="enchat-public-abcdefghijklmnopqrstuvwx",
            secret="b" * 43 + "=",
        )
        with patch.object(public_rooms, "list_active_rooms", return_value=[]):
            app = OnboardingApp("", "Wop")
            async with app.run_test(size=(100, 42)) as pilot:
                await pilot.pause()
                await pilot.click("#public-rooms")
                await pilot.pause()
                await pilot.click("#create")
                await pilot.pause()
                self.assertIsInstance(app.screen, PublicRoomCreateScreen)
                app.screen.query_one("#room", Input).value = "New room"
                with patch.object(public_rooms, "create_room", return_value=room), patch.object(
                    app, "exit"
                ) as exit_app:
                    app.screen.submit()
                result = exit_app.call_args.args[0]
                self.assertEqual(room.room_id, result.public_room_id)
                self.assertEqual("Wop", result.nick)

    async def test_public_room_actions_fit_a_narrow_terminal(self):
        with patch.object(public_rooms, "list_active_rooms", return_value=[]):
            app = OnboardingApp("", "Wop")
            async with app.run_test(size=(70, 38)) as pilot:
                await pilot.pause()
                await pilot.click("#public-rooms")
                await pilot.pause()
                card = app.screen.query_one(".form-card").region
                for button in app.screen.query(".public-actions Button"):
                    self.assertGreaterEqual(button.region.x, card.x)
                    self.assertLessEqual(
                        button.region.x + button.region.width,
                        card.x + card.width,
                    )

    async def test_public_directory_uses_requested_relay(self):
        with patch.object(public_rooms, "list_active_rooms", return_value=[]) as list_rooms:
            app = OnboardingApp("", "Wop", "https://custom-relay.example")
            async with app.run_test(size=(100, 42)) as pilot:
                await pilot.pause()
                await pilot.click("#public-rooms")
                await pilot.pause()
                list_rooms.assert_called_with("https://custom-relay.example")

    async def test_public_directory_error_is_visible(self):
        with patch.object(
            public_rooms,
            "list_active_rooms",
            side_effect=public_rooms.DirectoryUnavailable,
        ):
            app = OnboardingApp("", "Wop")
            async with app.run_test(size=(100, 42)) as pilot:
                await pilot.pause()
                await pilot.click("#public-rooms")
                await pilot.pause()
                status = app.screen.query_one("#directory-status", Static).renderable
                self.assertIn("unavailable", str(status).lower())


if __name__ == "__main__":
    unittest.main()
