import io
import unittest

from rich.console import Console, Group
from rich.markdown import Markdown

from chaos import config as config_mod
from chaos import ui


class RenderTest(unittest.TestCase):
    def test_reply_is_borderless_label_plus_markdown(self):
        rendered = ui.render_reply(config_mod.DEFAULT_THEME, "hello")
        self.assertIsInstance(rendered, Group)

    def test_reply_markdown_disables_terminal_hyperlinks(self):
        rendered = ui.render_reply(config_mod.DEFAULT_THEME, "[click](https://evil.example)")
        markdown = rendered.renderables[1]
        self.assertIsInstance(markdown, Markdown)
        self.assertFalse(markdown.hyperlinks)
        console = Console(file=io.StringIO(), width=80, force_terminal=True)
        console.print(rendered)
        out = console.file.getvalue()
        self.assertNotIn("\x1b]8", out)
        self.assertIn("https://evil.example", out)

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

    def test_ask_user_event_renders_question_and_numbered_choices(self):
        theme = config_mod.DEFAULT_THEME
        rendered = ui.render_ask_user(
            theme, {"type": "ask_user", "question": "which db?", "choices": ["postgres", "sqlite"]}
        )
        self.assertIsInstance(rendered, Group)
        plain = "\n".join(part.plain for part in rendered.renderables)
        self.assertIn("question: which db?", plain)
        self.assertNotIn("ask:", plain)
        self.assertIn("1. postgres", plain)
        self.assertIn("2. sqlite", plain)
        self.assertIn("reply with a number or free text", plain)

    def test_ask_user_event_without_choices_omits_the_hint(self):
        rendered = ui.render_ask_user(config_mod.DEFAULT_THEME, {"type": "ask_user", "question": "ok?"})
        plain = "\n".join(part.plain for part in rendered.renderables)
        self.assertIn("ok?", plain)
        self.assertNotIn("reply with", plain)

    def test_ask_user_tool_event_renders_question_and_answer(self):
        theme = config_mod.DEFAULT_THEME
        event = {
            "tool": "ask_user",
            "arguments": {"question": "which db?"},
            "result": {"ok": True, "answer": "sqlite"},
        }
        rendered = ui.render_tool(theme, event)
        self.assertIn("ask_user which db?", rendered.renderables[0].plain)
        self.assertIn("answer: sqlite", rendered.renderables[1].plain)

    def test_render_event_dispatches_on_type(self):
        theme = config_mod.DEFAULT_THEME
        round_event = ui.render_event(theme, {"type": "round", "reasoning": "hmm"})
        self.assertIsInstance(round_event, Group)
        call_event = ui.render_event(
            theme, {"type": "tool_call", "tool": "edit_file", "arguments": {"path": "a.py", "old_str": "x"}}
        )
        self.assertIn("edit_file a.py", call_event.plain)
        self.assertIn("…", call_event.plain)
        result_event = ui.render_event(
            theme,
            {
                "type": "tool_result",
                "tool": "edit_file",
                "arguments": {"path": "a.py", "old_str": "x", "new_str": "y"},
                "result": {"ok": True, "diff": "-x\n+y\n"},
            },
        )
        self.assertIsInstance(result_event, Group)
        self.assertIn("+y", result_event.renderables[1].plain)
        self.assertIsNone(ui.render_event(theme, {"type": "reply", "text": "done"}))
        self.assertIsNone(ui.render_event(theme, {"type": "round", "reasoning": ""}))

    def test_round_event_renders_reasoning_and_intermediate_content(self):
        theme = config_mod.DEFAULT_THEME
        rendered = ui.render_event(
            theme, {"type": "round", "reasoning": "hmm", "content": "let me look"}
        )
        self.assertIsInstance(rendered, Group)
        self.assertIn("hmm", rendered.renderables[0].renderables[1].plain)
        self.assertIn("let me look", rendered.renderables[1].plain)
        only_content = ui.render_event(theme, {"type": "round", "content": "checking files"})
        self.assertIn("checking files", only_content.renderables[0].plain)


class UsageTextTest(unittest.TestCase):
    def test_format_tokens_compacts_thousands_and_millions(self):
        self.assertEqual(ui.format_tokens(0), "0")
        self.assertEqual(ui.format_tokens(890), "890")
        self.assertEqual(ui.format_tokens(1000), "1k")
        self.assertEqual(ui.format_tokens(1200), "1.2k")
        self.assertEqual(ui.format_tokens(8900), "8.9k")
        self.assertEqual(ui.format_tokens(2500000), "2.5M")

    def test_usage_text_shows_this_turn_and_session_totals(self):
        text = ui.usage_text(
            {"prompt_tokens": 1200, "completion_tokens": 2200, "total_tokens": 3400}, 8900
        )
        self.assertEqual(text, "1.2k/3.4k tok this turn · 8.9k session")

    def test_usage_text_is_empty_when_nothing_was_used(self):
        self.assertEqual(ui.usage_text({}, 0), "")
        self.assertEqual(ui.usage_text(None, 0), "")
        self.assertEqual(ui.usage_text({"prompt_tokens": 0, "total_tokens": 0}, 0), "")


if __name__ == "__main__":
    unittest.main()
