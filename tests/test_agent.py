import unittest
from types import SimpleNamespace

from chaos.agent import MaxTurnsExceeded, run
from chaos.tools import schemas


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


class AgentLoopTest(unittest.TestCase):
    def test_tool_call_then_answer(self):
        responses = [
            SimpleNamespace(stop_reason="tool_use",
                            content=[tool_use_block("t1", "echo", {"text": "hi"})]),
            SimpleNamespace(stop_reason="end_turn", content=[text_block("done: hi")]),
        ]
        client = FakeClient(responses)
        messages = [{"role": "user", "content": "say hi"}]

        answer = run(client, messages, model="fake", max_turns=5)

        self.assertEqual(answer, "done: hi")
        self.assertEqual([m["role"] for m in messages],
                         ["user", "assistant", "user", "assistant"])
        tool_result = messages[2]["content"][0]
        self.assertEqual(tool_result["type"], "tool_result")
        self.assertEqual(tool_result["tool_use_id"], "t1")
        self.assertIn("hi", tool_result["content"])
        self.assertFalse(tool_result["is_error"])
        self.assertEqual(len(client.messages.calls), 2)

    def test_unknown_tool_returns_error_result(self):
        responses = [
            SimpleNamespace(stop_reason="tool_use",
                            content=[tool_use_block("t9", "nope", {})]),
            SimpleNamespace(stop_reason="end_turn", content=[text_block("ok")]),
        ]
        messages = [{"role": "user", "content": "x"}]

        answer = run(FakeClient(responses), messages, model="fake", max_turns=5)

        self.assertEqual(answer, "ok")
        self.assertTrue(messages[2]["content"][0]["is_error"])

    def test_max_turns_raises(self):
        responses = [
            SimpleNamespace(stop_reason="tool_use",
                            content=[tool_use_block(f"t{i}", "echo", {"text": "x"})])
            for i in range(10)
        ]
        with self.assertRaises(MaxTurnsExceeded):
            run(FakeClient(responses), [{"role": "user", "content": "loop"}],
                model="fake", max_turns=3)


class ToolSchemaTest(unittest.TestCase):
    def test_schemas_include_builtin_tools(self):
        by_name = {s["name"]: s for s in schemas()}
        self.assertIn("echo", by_name)
        echo = by_name["echo"]
        self.assertEqual(echo["input_schema"]["required"], ["text"])
        self.assertEqual(echo["input_schema"]["properties"]["text"]["type"], "string")
        self.assertTrue(echo["description"])

    def test_optional_params_not_required(self):
        by_name = {s["name"]: s for s in schemas()}
        self.assertEqual(by_name["list_files"]["input_schema"]["required"], [])


if __name__ == "__main__":
    unittest.main()
