import unittest

from enchat_lib import state
from enchat_lib.ui import ActionPalette, build_preview_app
from textual.widgets import Input, Static


class EnchatUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        state.room_participants.clear()

    async def test_preview_renders_messages_and_members(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            await pilot.pause()
            self.assertIn("#studio", app.query_one("#topbar", Static).renderable.plain)
            self.assertFalse(app.query_one("#members", Static).has_class("hidden"))
            self.assertEqual("Message #studio", app.query_one(Input).placeholder)

    async def test_unchanged_presence_does_not_redraw_sidebar(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            await pilot.pause()
            members = app.query_one("#members", Static)
            original_renderable = members.renderable
            app._sync_presence()
            self.assertIs(original_renderable, members.renderable)

    def test_participants_render_on_one_compact_line(self):
        app = build_preview_app()
        group = app._members_text(("Wop", "you"))
        lines = [renderable.plain for renderable in group.renderables]
        self.assertIn("Wop  • online", lines)
        self.assertIn("You  • online", lines)
        self.assertNotIn("   online", lines)

    async def test_members_hide_in_narrow_terminal(self):
        app = build_preview_app()
        async with app.run_test(size=(90, 35)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#members", Static).has_class("hidden"))

    async def test_ctrl_m_toggles_members(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            await pilot.press("ctrl+m")
            await pilot.pause()
            self.assertTrue(app.query_one("#members", Static).has_class("hidden"))

    async def test_ctrl_k_opens_action_palette(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            await pilot.press("ctrl+k")
            await pilot.pause()
            self.assertIsInstance(app.screen, ActionPalette)

    async def test_palette_share_action_prefills_command(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            await pilot.press("ctrl+k")
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ActionPalette)
            self.assertEqual("/share ", app.query_one("#composer", Input).value)

    async def test_submitting_message_appends_to_buffer(self):
        app = build_preview_app()
        async with app.run_test(size=(140, 46)) as pilot:
            composer = app.query_one("#composer", Input)
            composer.value = "A new message"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual("A new message", app.chat.buf[-1][1])
            self.assertTrue(app.chat.buf[-1][2])


if __name__ == "__main__":
    unittest.main()
