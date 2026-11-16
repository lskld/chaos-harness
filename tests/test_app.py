import asyncio
import threading
import unittest
from unittest.mock import patch

from textual.widgets import Footer, Input, RichLog, Static

from chaos import ui
from chaos.app import ChaosApp
from chaos.llm import Reply

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}


def log_text(app):
    return "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)


async def type_and_submit(app, pilot, text):
    app.query_one("#input", Input).value = text
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()


class AppTest(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_shows_thinking_and_reply(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", return_value=Reply(text="hello **world**", reasoning="hmm")):
                await type_and_submit(app, pilot, "hi")
            text = log_text(app)
            self.assertIn("hi", text)
            self.assertIn("hmm", text)
            self.assertIn("hello", text)
            self.assertEqual(app.messages[-1], {"role": "assistant", "content": "hello **world**"})
            self.assertEqual(str(app.query_one("#status", Static).render()), "")
            self.assertEqual(len(app.query(Footer)), 0)

    async def test_error_is_shown_and_user_message_popped(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", side_effect=Exception("boom")):
                await type_and_submit(app, pilot, "hi")
            self.assertIn("error: boom", log_text(app))
            self.assertEqual(app.messages, [])

    async def test_model_command_lists_and_switches(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model")
            self.assertIn("* p/m", log_text(app))
            self.assertIn("p/m2", log_text(app))
            await type_and_submit(app, pilot, "/model p/m2")
            self.assertEqual(app.ref, "p/m2")
            self.assertIn("switched to p/m2", log_text(app))

    async def test_mascot_and_spinner_animate_only_while_model_works(self):
        gate = threading.Event()

        def blocking_chat(**kwargs):
            gate.wait(10)
            return Reply(text="done")

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", side_effect=blocking_chat):
                app.query_one("#input", Input).value = "hi"
                await pilot.press("enter")
                await pilot.pause()
                await asyncio.sleep(0.4)
                self.assertIn("thinking", str(app.query_one("#status", Static).render()))
                mascot = str(app.query_one("#mascot", Static).render())
                self.assertTrue(any(f in mascot for f in ui.THINK_FACES))
                gate.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(str(app.query_one("#status", Static).render()), "")
                self.assertIn(ui.MASCOT_IDLE_FACE, str(app.query_one("#mascot", Static).render()))

    async def test_screen_background_comes_from_theme(self):
        from textual.color import Color

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            expected = Color.parse("#1a0d0a")
            self.assertEqual(app.screen.styles.background, expected)
            for selector in ("#topbar", "#log", "#input"):
                self.assertEqual(app.query_one(selector).styles.background, expected)

    async def test_clear_empties_log(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/clear")
            self.assertEqual(log_text(app).strip(), "")


if __name__ == "__main__":
    unittest.main()
