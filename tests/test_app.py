import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from textual.containers import VerticalScroll
from textual.widgets import Input, RichLog, Static

from chaos import ui
from chaos.app import ChaosApp, ThoughtProcess
from chaos.llm import Reply

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}

_console = Console(width=100)


def _renderable_text(renderable):
    with _console.capture() as capture:
        _console.print(renderable)
    return capture.get()


def log_text(app):
    parts = []
    for child in app.query_one("#log", VerticalScroll).children:
        if isinstance(child, ThoughtProcess):
            for event in child.events:
                rendered = ui.render_event(app.ui_theme, event)
                if rendered is not None:
                    parts.append(_renderable_text(rendered))
        elif isinstance(child, Static):
            parts.append(_renderable_text(child.content))
    return "\n".join(parts)


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

    async def test_tool_events_stream_into_the_thought_process_before_the_reply(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            Path(d, "a.py").write_text("x\n", encoding="utf-8")
            call = {
                "id": "1",
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "arguments": json.dumps({"path": "a.py", "old_str": "x", "new_str": "y"}),
                },
            }
            app = ChaosApp(cfg, "p/m")
            async with app.run_test() as pilot:
                with patch(
                    "chaos.agent.chat",
                    side_effect=[Reply(text="", tool_calls=(call,)), Reply(text="done")],
                ):
                    await type_and_submit(app, pilot, "hi")
                text = log_text(app)
                self.assertIn("edit_file a.py", text)
                self.assertIn("+y", text)
                self.assertIn("done", text)
                self.assertLess(text.index("edit_file a.py"), text.index("done"))

    async def test_thought_process_dropdown_is_collapsed_by_default_and_expandable(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", return_value=Reply(text="hi there", reasoning="hmm")):
                await type_and_submit(app, pilot, "hi")
            process = app.query_one(ThoughtProcess)
            self.assertTrue(process.collapsed)
            self.assertIn("hmm", log_text(app))
            process.collapsed = False
            await pilot.pause()
            self.assertFalse(process.collapsed)
            inner_lines = "\n".join(strip.text for strip in process.query_one(RichLog).lines)
            self.assertIn("hmm", inner_lines)

    async def test_thought_process_blends_with_app_background_and_dim_text(self):
        from textual.color import Color

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", return_value=Reply(text="hi", reasoning="hmm")):
                await type_and_submit(app, pilot, "hello")
            process = app.query_one(ThoughtProcess)
            for widget in [process, *process.query("*")]:
                self.assertEqual(widget.styles.background.a, 0, type(widget).__name__)
            log_bg = app.query_one("#log", VerticalScroll).styles.background
            self.assertEqual(log_bg, Color.parse("#1a0d0a"))
            inner = process.query_one(RichLog)
            self.assertEqual(inner.styles.color, Color.parse("#c4a3a3"))

    async def test_theme_switch_rebuilds_the_thought_process(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat", return_value=Reply(text="ok", reasoning="thinking hard")):
                await type_and_submit(app, pilot, "hi")
            await type_and_submit(app, pilot, "/theme mono")
            self.assertEqual(len(app.query(ThoughtProcess)), 1)
            self.assertIn("thinking hard", log_text(app))

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
