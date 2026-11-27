import concurrent.futures
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from chaos import commands, ui
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
            delta_buf = []
            for event in child.events:
                if event.get("type") == "delta":
                    if event.get("field") == "reasoning":
                        delta_buf.append(event.get("text", ""))
                    continue
                if delta_buf:
                    parts.append("".join(delta_buf))
                    delta_buf = []
                rendered = ui.render_event(app.ui_theme, event)
                if rendered is not None:
                    parts.append(_renderable_text(rendered))
            if delta_buf:
                parts.append("".join(delta_buf))
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
            with patch("chaos.agent.chat_stream", return_value=Reply(text="hello **world**", reasoning="hmm")):
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
                    "chaos.agent.chat_stream",
                    side_effect=[Reply(text="", tool_calls=(call,)), Reply(text="done")],
                ):
                    await type_and_submit(app, pilot, "hi")
                text = log_text(app)
                self.assertIn("edit_file a.py", text)
                self.assertIn("+y", text)
                self.assertIn("done", text)
                self.assertLess(text.index("edit_file a.py"), text.index("done"))

    async def test_tool_call_and_result_render_as_a_single_block(self):
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
                    "chaos.agent.chat_stream",
                    side_effect=[Reply(text="", tool_calls=(call,)), Reply(text="done")],
                ):
                    await type_and_submit(app, pilot, "hi")
                process = app.query_one(ThoughtProcess)
                blocks = [_renderable_text(w.content) for w in process.query(".process-log Static")]
                headers = [b for b in blocks if "edit_file a.py" in b]
                self.assertEqual(len(headers), 1)
                self.assertNotIn("…", headers[0])
                self.assertIn("+y", headers[0])

    async def test_ask_user_pauses_the_run_and_the_next_input_line_answers_it(self):
        app = ChaosApp(CFG, "p/m")
        call = {
            "id": "1",
            "type": "function",
            "function": {
                "name": "ask_user",
                "arguments": json.dumps(
                    {"question": "which db?", "choices": ["1. postgres", "2. sqlite"]}
                ),
            },
        }
        async with app.run_test() as pilot:
            with patch(
                "chaos.agent.chat_stream",
                side_effect=[Reply(text="", tool_calls=(call,)), Reply(text="using sqlite")],
            ):
                app.query_one("#input", Input).focus()
                app.query_one("#input", Input).value = "hi"
                await pilot.press("enter")
                for _ in range(100):
                    await pilot.pause(0.05)
                    if app._pending_ask is not None:
                        break
                self.assertIsNotNone(app._pending_ask)
                text = log_text(app)
                self.assertIn("which db?", text)
                self.assertIn("1. postgres", text)
                self.assertIn("2. sqlite", text)
                self.assertNotIn("1. 1.", text)
                self.assertNotIn("2. 2.", text)
                app.query_one("#input", Input).value = "2"
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                await pilot.pause()
            text = log_text(app)
            self.assertIn("using sqlite", text)
            self.assertIn("answer: sqlite", text)
            roles = [m["role"] for m in app.messages]
            self.assertEqual(roles.count("user"), 1)
            tool_msgs = [m for m in app.messages if m.get("role") == "tool"]
            self.assertEqual(len(tool_msgs), 1)
            self.assertIn('"answer": "sqlite"', tool_msgs[0]["content"])
            self.assertEqual(app.messages[-1], {"role": "assistant", "content": "using sqlite"})
            self.assertIsNone(app._pending_ask)

    async def test_a_new_ask_event_releases_the_previous_pending_future(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            process = ThoughtProcess(app.ui_theme, [])
            first, second = concurrent.futures.Future(), concurrent.futures.Future()
            app._add_process_event(process, {"type": "ask_user", "question": "q1", "choices": None, "future": first})
            self.assertIs(app._pending_ask["future"], first)
            app._add_process_event(process, {"type": "ask_user", "question": "q2", "choices": None, "future": second})
            self.assertIs(app._pending_ask["future"], second)
            self.assertTrue(first.done())
            with self.assertRaises(RuntimeError):
                first.result()

    async def test_fail_releases_a_pending_ask_future(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            future = concurrent.futures.Future()
            app._pending_ask = {"type": "ask_user", "question": "q", "choices": None, "future": future}
            app._fail(Exception("boom"))
            self.assertIsNone(app._pending_ask)
            self.assertTrue(future.done())
            with self.assertRaises(Exception):
                future.result()

    async def test_exit_releases_a_pending_ask_future(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            future = concurrent.futures.Future()
            app._pending_ask = {"type": "ask_user", "question": "q", "choices": None, "future": future}
            with patch.object(app, "exit") as exit_mock:
                app.action_exit_app()
            exit_mock.assert_called_once()
            self.assertIsNone(app._pending_ask)
            self.assertTrue(future.done())
            with self.assertRaises(RuntimeError):
                future.result()

    async def test_thought_process_dropdown_is_collapsed_by_default_and_expandable(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream", return_value=Reply(text="hi there", reasoning="hmm")):
                await type_and_submit(app, pilot, "hi")
            process = app.query_one(ThoughtProcess)
            self.assertTrue(process.collapsed)
            self.assertIn("hmm", log_text(app))
            process.collapsed = False
            await pilot.pause()
            self.assertFalse(process.collapsed)
            inner_text = "\n".join(
                _renderable_text(w.content) for w in process.query(".process-log Static")
            )
            self.assertIn("hmm", inner_text)

    async def test_thought_process_blends_with_app_background_and_dim_text(self):
        from textual.color import Color

        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream", return_value=Reply(text="hi", reasoning="hmm")):
                await type_and_submit(app, pilot, "hello")
            process = app.query_one(ThoughtProcess)
            for widget in [process, *process.query("*")]:
                self.assertEqual(widget.styles.background.a, 0, type(widget).__name__)
            log_bg = app.query_one("#log", VerticalScroll).styles.background
            self.assertEqual(log_bg, Color.parse("#1a0d0a"))
            inner = process.query_one(".process-log", VerticalScroll)
            self.assertEqual(inner.styles.color, Color.parse("#c4a3a3"))

    async def test_reasoning_streams_live_into_the_thought_process(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            def fake_stream(**kwargs):
                on_delta = kwargs["on_delta"]
                for chunk in ("I ", "should ", "bump x"):
                    on_delta("reasoning", chunk)
                on_delta("content", "done")
                return Reply(text="done", reasoning="I should bump x")

            with patch("chaos.agent.chat_stream", side_effect=fake_stream):
                await type_and_submit(app, pilot, "hi")
            process = app.query_one(ThoughtProcess)
            self.assertEqual(
                [e["type"] for e in process.events],
                ["delta", "delta", "delta", "delta", "reply"],
            )
            self.assertIn("I should bump x", log_text(app))
            self.assertIn("done", log_text(app))

    async def test_streamed_intermediate_text_stays_and_final_reply_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            Path(d, "a.py").write_text("x = 1\n", encoding="utf-8")
            app = ChaosApp(cfg, "p/m")
            call = {
                "id": "1",
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "arguments": json.dumps({"path": "a.py", "old_str": "x = 1", "new_str": "x = 2"}),
                },
            }
            state = {"n": 0}

            def fake_stream(**kwargs):
                state["n"] += 1
                on_delta = kwargs["on_delta"]
                if state["n"] == 1:
                    on_delta("content", "Let me check a.py. ")
                    return Reply(text="Let me check a.py. ", tool_calls=(call,))
                on_delta("content", "done")
                return Reply(text="done")

            async with app.run_test() as pilot:
                with patch("chaos.agent.chat_stream", side_effect=fake_stream):
                    await type_and_submit(app, pilot, "bump x")
                blocks = [str(w.content) for w in app.query_one(ThoughtProcess).query(".process-log Static")]
                joined = "|".join(blocks)
                self.assertIn("Let me check a.py.", joined)
                self.assertNotIn("done", joined)
                self.assertIn("done", log_text(app))

    async def test_theme_switch_rebuilds_the_thought_process(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream", return_value=Reply(text="ok", reasoning="thinking hard")):
                await type_and_submit(app, pilot, "hi")
            await type_and_submit(app, pilot, "/theme mono")
            self.assertEqual(len(app.query(ThoughtProcess)), 1)
            self.assertIn("thinking hard", log_text(app))

    async def test_error_is_shown_and_user_message_popped(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream", side_effect=Exception("boom")):
                await type_and_submit(app, pilot, "hi")
            self.assertIn("error: boom", log_text(app))
            self.assertEqual([m["role"] for m in app.messages], ["system"])

    async def test_second_submit_while_thinking_is_queued_and_run_after(self):
        app = ChaosApp(CFG, "p/m")
        started = threading.Event()
        release = threading.Event()

        def fake_stream(**kwargs):
            started.set()
            release.wait(timeout=10)
            return Reply(text="done")

        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream", side_effect=fake_stream) as stream_mock:
                app.query_one("#input", Input).focus()
                app.query_one("#input", Input).value = "first"
                await pilot.press("enter")
                for _ in range(100):
                    await pilot.pause(0.05)
                    if started.is_set():
                        break
                self.assertTrue(started.is_set())
                app.query_one("#input", Input).value = "second"
                await pilot.press("enter")
                app.query_one("#input", Input).value = "third"
                await pilot.press("enter")
                await pilot.pause()
                self.assertTrue(app._busy)
                self.assertEqual(stream_mock.call_count, 1)
                self.assertEqual(app._queued_inputs, ["second", "third"])
                self.assertIn("queued", log_text(app))
                release.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
            self.assertEqual(stream_mock.call_count, 3)
            self.assertFalse(app._busy)
            self.assertEqual(app._queued_inputs, [])
            self.assertEqual(
                [m["role"] for m in app.messages],
                ["system", "user", "assistant", "user", "assistant", "user", "assistant"],
            )
            self.assertEqual(
                [m["content"] for m in app.messages if m["role"] == "user"],
                ["first", "second", "third"],
            )

    async def test_fail_mid_tool_loop_rolls_history_back_to_before_the_user_message(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            call = {
                "id": "1",
                "type": "function",
                "function": {"name": "list_files", "arguments": "{}"},
            }
            app = ChaosApp(cfg, "p/m")
            async with app.run_test() as pilot:
                with patch(
                    "chaos.agent.chat_stream",
                    side_effect=[Reply(text="", tool_calls=(call,)), Exception("boom")],
                ):
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

    async def test_theme_picker_mouse_click_keeps_single_selection(self):
        from textual.widgets import SelectionList

        from chaos.app import ThemePicker

        app = ChaosApp(CFG, "p/m")
        async with app.run_test(size=(80, 24)) as pilot:
            await type_and_submit(app, pilot, "/theme")
            self.assertIsInstance(app.screen, ThemePicker)
            selection_list = app.screen.query_one("#list", SelectionList)
            self.assertEqual(selection_list.selected, ["fire"])
            await pilot.click("#list", offset=(2, 2))
            await pilot.pause()
            self.assertEqual(selection_list.selected, ["ocean"])
            await pilot.click("#list", offset=(2, 4))
            await pilot.pause()
            self.assertEqual(selection_list.selected, ["sunset"])
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.theme_name, "sunset")

    async def test_help_lists_commands(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/help")
            text = log_text(app)
            for cmd in ("/help", "/model", "/theme", "/deadline", "/clear", "/exit"):
                self.assertIn(cmd, text)

    async def test_bottom_bar_shows_the_workspace_directory_below_the_input(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            app = ChaosApp(cfg, "p/m")
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                cwd = app.query_one("#cwd", Static)
                self.assertIn(str(Path(d).resolve()), str(cwd.content))
                self.assertGreater(cwd.region.y, app.query_one("#input", Input).region.y)

    def test_cwd_text_compresses_the_home_directory(self):
        app = ChaosApp(CFG, "p/m")
        app.workspace_root = Path.home() / "proj"
        self.assertEqual(app._cwd_text(), "~/proj")
        app.workspace_root = Path("/tmp/elsewhere")
        self.assertEqual(app._cwd_text(), "/tmp/elsewhere")

    async def test_workspace_root_warning_is_logged_when_root_is_home(self):
        cfg = {**CFG, "workspace_root": str(Path.home())}
        app = ChaosApp(cfg, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIn("workspace root", log_text(app))

    async def test_clear_empties_log(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/clear")
            self.assertEqual(log_text(app).strip(), "")

    async def test_deadline_from_config_shows_in_top_bar_on_start(self):
        from datetime import datetime, timedelta

        future = (datetime.now().astimezone() + timedelta(hours=3)).isoformat(timespec="seconds")
        app = ChaosApp({**CFG, "deadline": future}, "p/m")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertRegex(str(app.query_one("#deadline", Static).render()), r"^⏳ [23]:\d{2} left$")

    async def test_expired_or_missing_deadline_keeps_top_bar_empty(self):
        from datetime import datetime, timedelta

        past = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat(timespec="seconds")
        for cfg in ({**CFG, "deadline": past}, CFG):
            app = ChaosApp(cfg, "p/m")
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(str(app.query_one("#deadline", Static).render()), "")

    async def test_deadline_command_updates_top_bar_and_persists(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            app = ChaosApp(CFG, "p/m", config_path=str(path))
            async with app.run_test() as pilot:
                await type_and_submit(app, pilot, "/deadline 23:59")
                self.assertRegex(
                    str(app.query_one("#deadline", Static).render()), r"^⏳ \d{1,2}:\d{2} left$"
                )
                self.assertIn("deadline set to", log_text(app))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("deadline", saved)

    async def test_deadline_off_clears_top_bar_and_config(self):
        import json
        import tempfile
        from datetime import datetime, timedelta
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat(timespec="seconds")
            seeded = dict(CFG, deadline=future)
            path.write_text(json.dumps(seeded), encoding="utf-8")
            app = ChaosApp(seeded, "p/m", config_path=str(path))
            async with app.run_test() as pilot:
                await type_and_submit(app, pilot, "/deadline off")
                self.assertEqual(str(app.query_one("#deadline", Static).render()), "")
                self.assertIn("deadline cleared", log_text(app))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("deadline", saved)

    async def test_typing_slash_lists_matching_commands_above_the_input(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#input", Input).focus()
            app.query_one("#input", Input).value = "/"
            await pilot.pause()
            widget = app.query_one("#suggestions", Static)
            self.assertTrue(widget.display)
            self.assertLess(widget.region.y, app.query_one("#input", Input).region.y)
            text = _renderable_text(widget.content)
            for command in commands.COMMANDS:
                self.assertIn(command, text)
            self.assertIn("pick a color theme", text)
            app.query_one("#input", Input).value = "/t"
            await pilot.pause()
            text = _renderable_text(widget.content)
            self.assertIn("/theme", text)
            self.assertNotIn("/deadline", text)
            app.query_one("#input", Input).value = "hello"
            await pilot.pause()
            self.assertFalse(widget.display)

    async def test_arrow_keys_move_the_highlight_and_tab_accepts_into_the_input(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            app.query_one("#input", Input).value = "/"
            await pilot.pause()
            self.assertEqual(app._suggestion_index, 0)
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(app._suggestion_index, 1)
            await pilot.press("up", "up")
            await pilot.pause()
            self.assertEqual(app._suggestion_index, len(commands.COMMANDS) - 1)
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#input", Input).value, "/exit")

    async def test_enter_accepts_a_partial_command_and_a_second_enter_submits_it(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            with patch("chaos.agent.chat_stream") as stream_mock:
                app.query_one("#input", Input).focus()
                app.query_one("#input", Input).value = "/he"
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.query_one("#input", Input).value, "/help")
                stream_mock.assert_not_called()
                self.assertEqual(app.messages, [])
                await pilot.press("enter")
                await pilot.pause()
            text = log_text(app)
            for cmd in ("/help", "/model", "/theme", "/deadline", "/clear", "/exit"):
                self.assertIn(cmd, text)

    async def test_accepting_a_command_with_an_arg_completes_the_arg_as_a_second_stage(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            app.query_one("#input", Input).value = "/theme o"
            await pilot.pause()
            widget = app.query_one("#suggestions", Static)
            self.assertTrue(widget.display)
            self.assertIn("ocean", _renderable_text(widget.content))
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#input", Input).value, "/theme ocean")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.theme_name, "ocean")

    async def test_arg_stage_completes_model_ids(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            app.query_one("#input", Input).value = "/model p/"
            await pilot.pause()
            text = _renderable_text(app.query_one("#suggestions", Static).content)
            self.assertIn("p/m2", text)
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#input", Input).value, "/model p/m")

    async def test_input_changed_from_another_widget_does_not_drive_suggestions(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            other = Input(id="other")
            await app.mount(other)
            app.query_one("#input", Input).value = "/t"
            await pilot.pause()
            self.assertEqual(app._suggestion_items, [("/theme", "pick a color theme")])
            app.on_input_changed(Input.Changed(other, "/d"))
            self.assertEqual(app._suggestion_items, [("/theme", "pick a color theme")])
            self.assertTrue(app.query_one("#suggestions", Static).display)
            await other.remove()

    async def test_escape_dismisses_the_list_until_the_input_changes_again(self):
        app = ChaosApp(CFG, "p/m")
        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            app.query_one("#input", Input).value = "/"
            await pilot.pause()
            self.assertTrue(app.query_one("#suggestions", Static).display)
            await pilot.press("escape")
            await pilot.pause()
            self.assertFalse(app.query_one("#suggestions", Static).display)
            app.query_one("#input", Input).value = "/d"
            await pilot.pause()
            widget = app.query_one("#suggestions", Static)
            self.assertTrue(widget.display)
            self.assertIn("/deadline", _renderable_text(widget.content))

    async def test_deadline_invalid_input_keeps_existing_deadline(self):
        from datetime import datetime, timedelta

        future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat(timespec="seconds")
        app = ChaosApp({**CFG, "deadline": future}, "p/m")
        async with app.run_test() as pilot:
            await type_and_submit(app, pilot, "/deadline soon")
            self.assertIn("HH:MM", log_text(app))
            self.assertEqual(app.cfg["deadline"], future)


if __name__ == "__main__":
    unittest.main()
