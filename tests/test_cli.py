import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from chaos import config as config_mod
from chaos.cli import repl
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


if __name__ == "__main__":
    unittest.main()
