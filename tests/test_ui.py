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


if __name__ == "__main__":
    unittest.main()
