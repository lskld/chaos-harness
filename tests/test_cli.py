import io
import json
import tempfile
import unittest
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
    def test_theme_command_is_handled_and_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/theme", "/theme mono", "/exit"], cfg, path)
            self.assertIn("fire", out)
            self.assertIn("ocean", out)
            self.assertNotIn("unknown theme", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["theme_name"], "mono")

    def test_model_command_switch_is_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/model p/m2", "/exit"], cfg, path)
            self.assertIn("switched to p/m2", out)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["default_model"], "p/m2")

    def test_unknown_theme_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(CFG), encoding="utf-8")
            cfg = config_mod.load(path)
            out = run_repl(["/theme nope", "/exit"], cfg, path)
            self.assertIn("unknown theme", out)

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


if __name__ == "__main__":
    unittest.main()
