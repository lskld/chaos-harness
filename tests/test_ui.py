import unittest

from rich.console import Group

from chaos import config as config_mod
from chaos import ui


class RenderTest(unittest.TestCase):
    def test_reply_is_borderless_label_plus_markdown(self):
        rendered = ui.render_reply(config_mod.DEFAULT_THEME, "hello")
        self.assertIsInstance(rendered, Group)

    def test_thinking_is_none_when_empty(self):
        self.assertIsNone(ui.render_thinking(config_mod.DEFAULT_THEME, ""))

    def test_thinking_renders_when_present(self):
        rendered = ui.render_thinking(config_mod.DEFAULT_THEME, "hmm")
        self.assertIsInstance(rendered, Group)

    def test_tool_event_renders_header_and_diff(self):
        event = {
            "tool": "edit_file",
            "arguments": {"path": "a.py", "old_str": "x", "new_str": "y"},
            "result": {"ok": True, "diff": "-x\n+y\n"},
        }
        rendered = ui.render_tool(config_mod.DEFAULT_THEME, event)
        self.assertIsInstance(rendered, Group)
        self.assertIn("edit_file a.py", rendered.renderables[0].plain)
        self.assertIn("+y", rendered.renderables[1].plain)

    def test_tool_event_renders_error(self):
        event = {"tool": "read_file", "arguments": {"path": "x"}, "result": {"ok": False, "error": "nope"}}
        rendered = ui.render_tool(config_mod.DEFAULT_THEME, event)
        self.assertIn("error: nope", rendered.renderables[1].plain)


if __name__ == "__main__":
    unittest.main()
