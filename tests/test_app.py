import unittest
from unittest.mock import patch

from textual.widgets import Input, RichLog, Static

from chaos.app import ChaosApp
from chaos.llm import Reply

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}


def log_text(app):
    return "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)


async def type_and_submit(app, pilot, text):
    app.query_one("#input", Input).focus()
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

    async def test_tool_events_are_logged_before_the_reply(self):
        event = {
            "tool": "edit_file",
            "arguments": {"path": "a.py", "old_str": "x", "new_str": "y"},
            "result": {"ok": True, "diff": "-x\n+y\n"},
        }
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch(
                "chaos.app.respond", return_value=Reply(text="done", events=(event,))
            ):
                await type_and_submit(app, pilot, "hi")
            text = log_text(app)
            self.assertIn("edit_file a.py", text)
            self.assertIn("+y", text)
            self.assertIn("done", text)

    async def test_error_is_shown_and_user_message_popped(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", side_effect=Exception("boom")):
                await type_and_submit(app, pilot, "hi")
            self.assertIn("error: boom", log_text(app))
            self.assertEqual([m["role"] for m in app.messages], ["system"])

    async def test_model_command_without_arg_opens_picker(self):
        from chaos.app import ModelPicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model")
            self.assertIsInstance(app.screen, ModelPicker)

    async def test_model_command_switches_directly_and_rejects_unknown(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model p/m2")
            self.assertEqual(app.ref, "p/m2")
            self.assertEqual(str(app.query_one("#model", Static).render()), "model: p/m2")
            self.assertIn("switched to p/m2", log_text(app))
            await type_and_submit(app, pilot, "/model nope/x")
            self.assertEqual(app.ref, "p/m2")
            self.assertIn("unknown provider", log_text(app))

    async def test_model_picker_modal_switches_with_arrow_keys(self):
        from chaos.app import ModelPicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model")
            self.assertIsInstance(app.screen, ModelPicker)
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertEqual(app.ref, "p/m2")
            self.assertEqual(str(app.query_one("#model", Static).render()), "model: p/m2")
            self.assertIn("switched to p/m2", log_text(app))

    async def test_model_picker_escape_keeps_model(self):
        from chaos.app import ModelPicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model")
            self.assertIsInstance(app.screen, ModelPicker)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.ref, "p/m")

    async def test_model_picker_with_no_models_logs_error(self):
        from chaos.app import ModelPicker

        cfg = {"default_model": "p/m", "providers": {"p": {"base_url": "u", "api_key": "k", "models": []}}}
        app = ChaosApp(cfg, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/model")
            self.assertNotIsInstance(app.screen, ModelPicker)
            self.assertIn("no models configured", log_text(app))

    async def test_model_choice_is_saved_to_config_and_used_on_restart(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            app = ChaosApp(CFG, "p/m", config_path=str(path))
            async with app.run_test() as pilot:
                await type_and_submit(app, pilot, "/model")
                await pilot.press("down", "enter")
                await pilot.pause()
                self.assertEqual(app.ref, "p/m2")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["default_model"], "p/m2")
            restarted = ChaosApp(saved, saved.get("default_model"), config_path=str(path))
            self.assertEqual(restarted.ref, "p/m2")

    async def test_model_direct_switch_is_saved_to_config(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            app = ChaosApp(CFG, "p/m", config_path=str(path))
            async with app.run_test() as pilot:
                await type_and_submit(app, pilot, "/model p/m2")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["default_model"], "p/m2")

    async def test_screen_background_comes_from_theme(self):
        from textual.color import Color

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            expected = Color.parse("#1a0d0a")
            self.assertEqual(app.screen.styles.background, expected)
            for selector in ("#topbar", "#log", "#input"):
                self.assertEqual(app.query_one(selector).styles.background, expected)

    async def test_theme_picker_modal_switches_with_arrow_keys(self):
        from textual.color import Color

        from chaos.app import ThemePicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/theme")
            self.assertIsInstance(app.screen, ThemePicker)
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertEqual(app.theme_name, "ocean")
            self.assertEqual(app.screen.styles.background, Color.parse("#0a1420"))
            self.assertEqual(
                app.query_one("#mascot", Static).styles.background, Color.parse("#0a1420")
            )

    async def test_theme_direct_name_and_unknown(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/theme mono")
            self.assertEqual(app.theme_name, "mono")
            await type_and_submit(app, pilot, "/theme nope")
            self.assertIn("unknown theme", log_text(app))

    async def test_theme_choice_is_saved_to_config_and_used_on_restart(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            app = ChaosApp(CFG, "p/m", config_path=str(path))
            async with app.run_test() as pilot:
                await type_and_submit(app, pilot, "/theme mono")
                self.assertEqual(app.theme_name, "mono")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["theme_name"], "mono")
            restarted = ChaosApp(saved, "p/m", config_path=str(path))
            self.assertEqual(restarted.theme_name, "mono")

    async def test_pickers_are_centered_in_the_terminal(self):
        from chaos.app import ModelPicker, ThemePicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test(size=(80, 24)) as pilot:
            for command, picker_cls in (("/model", ModelPicker), ("/theme", ThemePicker)):
                await type_and_submit(app, pilot, command)
                self.assertIsInstance(app.screen, picker_cls)
                region = app.screen.query_one("#picker").region
                self.assertEqual((region.x, region.y), ((80 - region.width) // 2, (24 - region.height) // 2))
                await pilot.press("escape")
                await pilot.pause()

    async def test_theme_picker_escape_keeps_theme(self):
        from chaos.app import ThemePicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/theme")
            self.assertIsInstance(app.screen, ThemePicker)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.theme_name, "fire")

    async def test_help_lists_commands(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/help")
            text = log_text(app)
            for cmd in ("/help", "/model", "/theme", "/clear", "/exit"):
                self.assertIn(cmd, text)

    async def test_clear_empties_log(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/clear")
            self.assertEqual(log_text(app).strip(), "")


if __name__ == "__main__":
    unittest.main()
