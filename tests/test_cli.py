import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from chaos import config as config_mod
from chaos.cli import main, repl
from chaos.llm import Reply

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}


def run_repl(lines, cfg, path, ref="p/m"):
    console = Console(file=io.StringIO(), width=100)
    inputs = iter(lines)

    def fake_prompt(*args, **kwargs):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch("chaos.ui.prompt_input", side_effect=fake_prompt):
        repl(console, config_mod.theme(cfg), cfg, ref, str(path))
    return console.file.getvalue()


class ReplCommandTest(unittest.TestCase):
    def test_model_and_theme_commands_switch_and_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/model p/m2", "/theme mono", "/exit"], cfg, path)
            self.assertIn("switched to p/m2", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["default_model"], "p/m2")
            self.assertEqual(saved["theme_name"], "mono")

    def test_unknown_theme_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/theme nope", "/exit"], cfg, path)
            self.assertIn("unknown theme", out)

    def test_deadline_command_persists_iso_value(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/deadline 23:59", "/exit"], cfg, path)
            self.assertIn("deadline set to", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(datetime.fromisoformat(saved["deadline"]).tzinfo)

    def test_deadline_off_removes_key_and_invalid_keeps_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            seeded = dict(CFG, deadline="2026-11-20T17:00:00+01:00")
            path.write_text(json.dumps(seeded), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/deadline nope", "/exit"], cfg, path)
            self.assertIn("HH:MM", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["deadline"], "2026-11-20T17:00:00+01:00")
            out = run_repl(["/deadline off", "/exit"], cfg, path)
            self.assertIn("deadline cleared", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("deadline", saved)

    def test_plain_text_still_goes_to_the_model(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            with patch("chaos.cli.respond", return_value=Reply(text="yo")):
                out = run_repl(["hi", "/exit"], cfg, path)
            self.assertIn("yo", out)

    def test_tool_events_are_printed_in_the_repl(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            event = {
                "tool": "write_file",
                "arguments": {"path": "x.py", "content": "print(1)"},
                "result": {"ok": True, "bytes": 8},
            }
            with patch("chaos.cli.respond", return_value=Reply(text="yo", events=(event,))):
                out = run_repl(["hi", "/exit"], cfg, path)
            self.assertIn("write_file x.py", out)
            self.assertIn("yo", out)


    def test_help_lists_commands_and_blank_lines_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/help", "", "/exit"], cfg, path)
            for cmd in ("/help", "/model", "/theme", "/clear", "/exit"):
                self.assertIn(cmd, out)

    def test_clear_empties_history(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            with patch(
                "chaos.cli.respond", side_effect=[Reply(text="first"), Reply(text="second")]
            ) as respond_mock:
                out = run_repl(["hi", "/clear", "again", "/exit"], cfg, path)
            self.assertIn("history cleared", out)
            self.assertIn("second", out)
            self.assertEqual(
                respond_mock.call_args_list[1].args[2], [{"role": "user", "content": "again"}]
            )

    def test_eof_at_prompt_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl([], cfg, path)
            self.assertIn("p/m", out)

    def test_error_from_model_is_printed_and_message_popped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            with patch(
                "chaos.cli.respond", side_effect=[Exception("boom"), Reply(text="ok")]
            ) as respond_mock:
                out = run_repl(["hi", "again", "/exit"], cfg, path)
            self.assertIn("error: boom", out)
            self.assertIn("ok", out)
            self.assertEqual(
                respond_mock.call_args_list[1].args[2], [{"role": "user", "content": "again"}]
            )

    def test_keyboard_interrupt_during_model_call_pops_message(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            with patch(
                "chaos.cli.respond", side_effect=[KeyboardInterrupt(), Reply(text="ok")]
            ) as respond_mock:
                out = run_repl(["hi", "again", "/exit"], cfg, path)
            self.assertIn("ok", out)
            self.assertEqual(
                respond_mock.call_args_list[1].args[2], [{"role": "user", "content": "again"}]
            )


class ReplAskUserTest(unittest.TestCase):
    def _ask_call(self):
        return {
            "id": "1",
            "type": "function",
            "function": {
                "name": "ask_user",
                "arguments": json.dumps({"question": "which db?", "choices": ["postgres", "sqlite"]}),
            },
        }

    def _run_with_stdin(self, stdin_text, cfg, path):
        calls = [Reply(text="", tool_calls=(self._ask_call(),)), Reply(text="using sqlite")]
        with (
            patch("chaos.agent.chat", side_effect=calls) as chat_mock,
            patch("sys.stdin", io.StringIO(stdin_text)),
        ):
            out = run_repl(["hi", "/exit"], cfg, path)
        return out, chat_mock

    def test_repl_prints_the_question_and_reads_a_choice_number_from_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out, chat_mock = self._run_with_stdin("2\n", cfg, path)
            self.assertIn("which db?", out)
            self.assertIn("1) postgres", out)
            self.assertIn("2) sqlite", out)
            self.assertIn("using sqlite", out)
            tool_msg = chat_mock.call_args_list[1].kwargs["messages"][3]
            self.assertIn('"answer": "sqlite"', tool_msg["content"])

    def test_repl_ask_user_free_text_answer_from_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            _, chat_mock = self._run_with_stdin("mysql\n", cfg, path)
            tool_msg = chat_mock.call_args_list[1].kwargs["messages"][3]
            self.assertIn('"answer": "mysql"', tool_msg["content"])

    def test_repl_ask_user_eof_on_stdin_gives_an_empty_answer(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            _, chat_mock = self._run_with_stdin("", cfg, path)
            tool_msg = chat_mock.call_args_list[1].kwargs["messages"][3]
            self.assertIn('"answer": ""', tool_msg["content"])


class MainTest(unittest.TestCase):
    def test_main_warns_loudly_when_workspace_root_is_home(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("os.getcwd", return_value=str(Path.home())),
                patch("chaos.cli.respond", return_value=Reply(text="yo")),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("warning", out)
            self.assertIn("workspace root", out)

    def test_main_stays_quiet_for_a_plain_project_root(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cfgdir:
            path = Path(cfgdir) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("os.getcwd", return_value=d),
                patch("chaos.cli.respond", return_value=Reply(text="yo")),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 0)
            self.assertNotIn("warning", buf.getvalue())

    def test_one_shot_prints_model_output_literally(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("chaos.cli.respond", return_value=Reply(text="[red]not styled[/]")),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 0)
            self.assertIn("[red]not styled[/]", buf.getvalue())

    def test_main_reports_friendly_error_when_config_dir_is_unwritable(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            path = blocker / "config.json"
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 2)
            out = buf.getvalue()
            self.assertIn("error:", out)
            self.assertIn("cannot write example config", out)
            self.assertNotIn("Traceback", out)


    def test_model_flag_overrides_config_default(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("chaos.cli.respond", return_value=Reply(text="yo")) as respond_mock,
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "--model", "p/m2", "hi"])
            self.assertEqual(rc, 0)
            self.assertEqual(respond_mock.call_args.args[1], "p/m2")

    def test_one_shot_invalid_model_returns_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("chaos.cli.respond") as respond_mock,
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "--model", "nope/x", "hi"])
            self.assertEqual(rc, 2)
            self.assertIn("unknown provider", buf.getvalue())
            respond_mock.assert_not_called()

    def test_one_shot_keyboard_interrupt_returns_130(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("chaos.cli.respond", side_effect=KeyboardInterrupt),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 130)

    def test_one_shot_unexpected_error_prints_error_and_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch("chaos.cli.respond", side_effect=RuntimeError("boom")),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 1)
            self.assertIn("error: boom", buf.getvalue())

    def test_one_shot_prints_the_question_and_reads_the_answer_from_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            call = {
                "id": "1",
                "type": "function",
                "function": {
                    "name": "ask_user",
                    "arguments": json.dumps({"question": "which db?", "choices": ["postgres", "sqlite"]}),
                },
            }
            calls = [Reply(text="", tool_calls=(call,)), Reply(text="done with sqlite")]
            with (
                patch("chaos.agent.chat", side_effect=calls),
                patch("sys.stdin", io.StringIO("2\n")),
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path), "hi"])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("which db?", out)
            self.assertIn("done with sqlite", out)

    def test_main_launches_app_on_a_tty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch.object(sys.stdin, "isatty", return_value=True),
                patch("chaos.app.ChaosApp") as app_cls,
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path)])
            self.assertEqual(rc, 0)
            app_cls.assert_called_once()
            app_cls.return_value.run.assert_called_once()

    def test_main_runs_repl_when_piped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            buf = io.StringIO()
            with (
                patch.object(sys.stdin, "isatty", return_value=False),
                patch("chaos.cli.repl") as repl_mock,
                patch("sys.stdout", buf),
            ):
                rc = main(["--config", str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(repl_mock.call_args.args[4], str(path))


if __name__ == "__main__":
    unittest.main()
