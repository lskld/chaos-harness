import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chaos.agent import respond
from chaos.llm import Reply

CFG = {"providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m"]}}}


class RespondTest(unittest.TestCase):
    def test_appends_assistant_reply(self):
        messages = [{"role": "user", "content": "hi"}]
        with patch("chaos.agent.chat", return_value=Reply(text="yo", reasoning="hmm")) as chat_mock:
            reply = respond(CFG, "p/m", messages)
        self.assertEqual(reply.text, "yo")
        self.assertEqual(reply.reasoning, "hmm")
        self.assertEqual(messages[-1], {"role": "assistant", "content": "yo"})
        self.assertEqual(chat_mock.call_args.kwargs["model"], "m")
        self.assertEqual(chat_mock.call_args.kwargs["base_url"], "https://x/v1")
        self.assertEqual(reply.events, ())

    def test_system_prompt_is_inserted_once(self):
        messages = [{"role": "user", "content": "hi"}]
        with patch("chaos.agent.chat", return_value=Reply(text="yo")):
            respond(CFG, "p/m", messages)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("workspace rooted at", messages[0]["content"])
        self.assertIn("never list or read the workspace", messages[0]["content"])
        self.assertIn("without any tool call", messages[0]["content"])
        with patch("chaos.agent.chat", return_value=Reply(text="again")):
            respond(CFG, "p/m", messages)
        self.assertEqual([m["role"] for m in messages].count("system"), 1)


class ToolLoopTest(unittest.TestCase):
    def test_tool_calls_are_executed_and_looped_until_final_reply(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            Path(d, "f.txt").write_text("hello\n", encoding="utf-8")
            messages = [{"role": "user", "content": "change f.txt"}]
            edit_args = json.dumps({"path": "f.txt", "old_str": "hello", "new_str": "bye"})
            edit_call = {
                "id": "1",
                "type": "function",
                "function": {"name": "edit_file", "arguments": edit_args},
            }
            calls = [
                Reply(text="", tool_calls=(edit_call,)),
                Reply(text="done"),
            ]
            with patch("chaos.agent.chat", side_effect=calls) as chat_mock:
                reply = respond(cfg, "p/m", messages)
            self.assertEqual(reply.text, "done")
            self.assertEqual(Path(d, "f.txt").read_text(encoding="utf-8"), "bye\n")
            self.assertEqual(
                [m["role"] for m in messages],
                ["system", "user", "assistant", "tool", "assistant"],
            )
            echoed = messages[2]["tool_calls"][0]
            self.assertEqual(set(echoed), {"id", "type", "function"})
            self.assertEqual(echoed["type"], "function")
            self.assertEqual(echoed["function"]["name"], "edit_file")
            self.assertEqual(echoed["function"]["arguments"], edit_args)
            self.assertEqual(messages[3]["tool_call_id"], "1")
            self.assertEqual(messages[3]["name"], "edit_file")
            self.assertIn('"ok": true', messages[3]["content"])
            self.assertEqual(len(reply.events), 1)
            self.assertEqual(reply.events[0]["tool"], "edit_file")
            self.assertEqual(reply.events[0]["arguments"]["path"], "f.txt")
            self.assertTrue(reply.events[0]["result"]["ok"])
            self.assertIn("tools", chat_mock.call_args.kwargs)

    def test_failed_tool_call_is_reported_back_to_the_model(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d}
            messages = [{"role": "user", "content": "go"}]
            calls = [
                Reply(
                    text="",
                    tool_calls=(
                        {
                            "id": "1",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps({"path": "gone.txt", "old_str": "a", "new_str": "b"}),
                            },
                        },
                    ),
                ),
                Reply(text="could not"),
            ]
            with patch("chaos.agent.chat", side_effect=calls):
                reply = respond(cfg, "p/m", messages)
            self.assertEqual(reply.text, "could not")
            self.assertEqual(messages[3]["role"], "tool")
            self.assertIn('"ok": false', messages[3]["content"])
            self.assertFalse(reply.events[0]["result"]["ok"])

    def test_tool_round_limit_stops_the_loop(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {**CFG, "workspace_root": d, "max_tool_rounds": 2}
            messages = [{"role": "user", "content": "go"}]
            call = {
                "id": "1",
                "type": "function",
                "function": {"name": "list_files", "arguments": "{}"},
            }
            with patch("chaos.agent.chat", return_value=Reply(text="", tool_calls=(call,))) as chat_mock:
                reply = respond(cfg, "p/m", messages)
            self.assertIn("stopped after 2 tool rounds", reply.text)
            self.assertEqual(chat_mock.call_count, 2)
            self.assertEqual(len(reply.events), 2)
            self.assertEqual(messages[-1], {"role": "assistant", "content": reply.text})


if __name__ == "__main__":
    unittest.main()
