import unittest
from unittest.mock import Mock, patch

import requests

from chaos.llm import LLMError, add_usage, chat, chat_stream


def fake_response(status=200, payload=None, text=""):
    response = Mock()
    response.status_code = status
    response.json = lambda: payload
    response.text = text
    return response


def payload(content=None, reasoning=None, extra_message=None, usage=None):
    message = {"content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    if extra_message:
        message.update(extra_message)
    body = {"choices": [{"message": message}]}
    if usage is not None:
        body["usage"] = usage
    return body


class ChatTest(unittest.TestCase):
    def test_posts_openai_compatible_payload(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content="hello there"))
            reply = chat(
                base_url="https://api.example.com/v1/",
                api_key="sk-test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        self.assertEqual(reply.text, "hello there")
        self.assertEqual(reply.reasoning, "")
        self.assertEqual(post.call_args.args[0], "https://api.example.com/v1/chat/completions")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(
            kwargs["json"],
            {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )

    def test_http_error_raises_llm_error(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(status=401, text="unauthorized")
            with self.assertRaises(LLMError) as ctx:
                chat(base_url="https://api.example.com/v1", api_key="bad", model="m", messages=[])
        self.assertIn("401", str(ctx.exception))

    def test_http_error_redacts_api_key_from_response_text(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(status=500, text='echo "sk-live-abcdef123456"')
            with self.assertRaises(LLMError) as ctx:
                chat(
                    base_url="https://api.example.com/v1",
                    api_key="sk-live-abcdef123456",
                    model="m",
                    messages=[],
                )
        self.assertIn("500", str(ctx.exception))
        self.assertNotIn("sk-live-abcdef123456", str(ctx.exception))
        self.assertIn("***redacted***", str(ctx.exception))

    def test_network_error_raises_llm_error(self):
        with patch("chaos.llm.requests.post", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(LLMError):
                chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])

    def test_malformed_payload_raises_llm_error(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload={"unexpected": True})
            with self.assertRaises(LLMError):
                chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])

    def test_list_content_parts_are_joined(self):
        content = [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "hel"},
            {"type": "text", "text": "lo"},
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content=content))
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hello")

    def test_none_content_returns_empty_string(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content=None))
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "")

    def test_reasoning_field_is_extracted(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(
                payload=payload(content="answer", reasoning="step by step")
            )
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "answer")
        self.assertEqual(reply.reasoning, "step by step")

    def test_reasoning_content_field_is_extracted(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(
                payload=payload(content="a", extra_message={"reasoning_content": "thinking..."})
            )
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.reasoning, "thinking...")

    def test_thinking_field_is_extracted(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(
                payload=payload(content="a", extra_message={"thinking": "ollama style"})
            )
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.reasoning, "ollama style")

    def test_tools_are_sent_in_payload_when_given(self):
        tools_payload = [{"type": "function", "function": {"name": "read_file"}}]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content="hi"))
            chat(
                base_url="https://api.example.com/v1",
                api_key="k",
                model="m",
                messages=[],
                tools=tools_payload,
            )
        self.assertEqual(post.call_args.kwargs["json"]["tools"], tools_payload)

    def test_tools_are_omitted_from_payload_by_default(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content="hi"))
            chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertNotIn("tools", post.call_args.kwargs["json"])

    def test_tool_calls_are_parsed_into_canonical_shape(self):
        message = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "edit_file", "arguments": '{"path": "a.py"}'},
                }
            ],
        }
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload={"choices": [{"message": message}]})
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(
            reply.tool_calls,
            (
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "edit_file", "arguments": '{"path": "a.py"}'},
                },
            ),
        )
        self.assertEqual(reply.text, "")

    def test_tool_call_arguments_given_as_object_are_serialized(self):
        message = {
            "content": "",
            "tool_calls": [
                {"id": "c", "function": {"name": "read_file", "arguments": {"path": "a.py"}}}
            ],
        }
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload={"choices": [{"message": message}]})
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.tool_calls[0]["function"]["arguments"], '{"path": "a.py"}')

    def test_no_tool_calls_by_default(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content="hi"))
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.tool_calls, ())
        self.assertEqual(reply.events, ())
        self.assertEqual(reply.usage, {})

    def test_usage_block_lands_on_reply(self):
        usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=payload(content="hi", usage=usage))
            reply = chat(base_url="https://api.example.com/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hi")
        self.assertEqual(reply.usage, usage)


def sse_response(lines, status=200, text=""):
    response = Mock()
    response.status_code = status
    response.headers = {"Content-Type": "text/event-stream"}
    response.iter_lines = lambda decode_unicode=False: iter(lines)
    response.text = text
    return response


class ChatStreamTest(unittest.TestCase):
    def test_streams_deltas_and_accumulates_reply(self):
        lines = [
            'data: {"choices": [{"delta": {"reasoning": "think "}}]}',
            "",
            'data: {"choices": [{"delta": {"reasoning_content": "hard"}}]}',
            'data: {"choices": [{"delta": {"content": "hel"}}]}',
            'data: {"choices": [{"delta": {"content": "lo"}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "read_file", "arguments": "{\\"path\\": "}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\\"a.py\\"}"}}]}}]}',
            "data: [DONE]",
            'data: {"choices": [{"delta": {"content": "ignored after done"}}]}',
        ]
        deltas = []
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(
                base_url="https://x/v1",
                api_key="k",
                model="m",
                messages=[],
                on_delta=lambda field, text: deltas.append((field, text)),
            )
        self.assertEqual(reply.text, "hello")
        self.assertEqual(reply.reasoning, "think hard")
        self.assertEqual(
            reply.tool_calls,
            (
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                },
            ),
        )
        self.assertEqual(
            deltas,
            [("reasoning", "think "), ("reasoning", "hard"), ("content", "hel"), ("content", "lo")],
        )
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertTrue(post.call_args.kwargs["stream"])

    def test_indexless_tool_call_deltas_with_ids_stay_separate(self):
        lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": "{\\"path\\": "}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"id": "c2", "function": {"name": "list_files", "arguments": "{}"}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"id": "c1", "function": {"arguments": "\\"a.py\\"}"}}]}}]}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(len(reply.tool_calls), 2)
        self.assertEqual(reply.tool_calls[0]["id"], "c1")
        self.assertEqual(reply.tool_calls[0]["function"]["name"], "read_file")
        self.assertEqual(reply.tool_calls[0]["function"]["arguments"], '{"path": "a.py"}')
        self.assertEqual(reply.tool_calls[1]["id"], "c2")
        self.assertEqual(reply.tool_calls[1]["function"]["name"], "list_files")
        self.assertEqual(reply.tool_calls[1]["function"]["arguments"], "{}")

    def test_indexless_and_idless_tool_call_deltas_get_fresh_keys(self):
        lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"function": {"name": "read_file", "arguments": "{}"}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"function": {"name": "list_files", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(len(reply.tool_calls), 2)
        self.assertEqual(reply.tool_calls[0]["function"]["name"], "read_file")
        self.assertEqual(reply.tool_calls[1]["function"]["name"], "list_files")

    def test_hybrid_deltas_with_index_then_id_only_stay_merged(self):
        lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "read_file", "arguments": "{\\"path\\": "}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"id": "c1", "function": {"arguments": "\\"a.py\\"}"}}]}}]}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(len(reply.tool_calls), 1)
        self.assertEqual(reply.tool_calls[0]["id"], "c1")
        self.assertEqual(reply.tool_calls[0]["function"]["name"], "read_file")
        self.assertEqual(reply.tool_calls[0]["function"]["arguments"], '{"path": "a.py"}')

    def test_id_only_delta_then_index_delta_with_same_id_stay_merged(self):
        lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": "{\\"path\\": "}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"arguments": "\\"a.py\\"}"}}]}}]}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(len(reply.tool_calls), 1)
        self.assertEqual(reply.tool_calls[0]["id"], "c1")
        self.assertEqual(reply.tool_calls[0]["function"]["name"], "read_file")
        self.assertEqual(reply.tool_calls[0]["function"]["arguments"], '{"path": "a.py"}')

    def test_stream_content_as_list_of_text_parts_is_accumulated(self):
        lines = [
            'data: {"choices": [{"delta": {"content": [{"type": "text", "text": "hel"}]}}]}',
            'data: {"choices": [{"delta": {"content": [{"type": "text", "text": "lo"}]}}]}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hello")

    def test_max_tokens_is_sent_only_when_set(self):
        with patch("chaos.llm.requests.post") as post:
            response = fake_response(payload=payload(content="hi"))
            response.headers = {"Content-Type": "application/json"}
            post.return_value = response
            chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
            self.assertNotIn("max_tokens", post.call_args.kwargs["json"])
            chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[], max_tokens=4096)
            self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 4096)

    def test_non_sse_response_falls_back_to_plain_parsing(self):
        with patch("chaos.llm.requests.post") as post:
            response = fake_response(payload=payload(content="hi", reasoning="hmm"))
            response.headers = {"Content-Type": "application/json"}
            post.return_value = response
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hi")
        self.assertEqual(reply.reasoning, "hmm")

    def test_http_error_raises_llm_error(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response([], status=500, text="boom")
            with self.assertRaises(LLMError) as ctx:
                chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertIn("500", str(ctx.exception))

    def test_network_error_raises_llm_error(self):
        with patch("chaos.llm.requests.post", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(LLMError):
                chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])

    def test_stream_delta_thinking_field_is_treated_as_reasoning(self):
        lines = [
            'data: {"choices": [{"delta": {"thinking": "hmm "}}]}',
            'data: {"choices": [{"delta": {"thinking": "deep"}}]}',
            'data: {"choices": [{"delta": {"content": "answer"}}]}',
            "data: [DONE]",
        ]
        deltas = []
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(
                base_url="https://x/v1",
                api_key="k",
                model="m",
                messages=[],
                on_delta=lambda field, text: deltas.append((field, text)),
            )
        self.assertEqual(reply.reasoning, "hmm deep")
        self.assertEqual(reply.text, "answer")
        self.assertEqual(deltas[0], ("reasoning", "hmm "))

    def test_malformed_sse_lines_are_skipped(self):
        lines = ["data: not json", 'data: {"unexpected": 1}', 'data: {"choices": [{"delta": {"content": "ok"}}]}', "data: [DONE]"]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "ok")
        self.assertEqual(reply.usage, {})

    def test_stream_requests_usage_via_stream_options(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(["data: [DONE]"])
            chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(post.call_args.kwargs["json"]["stream_options"], {"include_usage": True})

    def test_stream_usage_chunk_lands_on_reply(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "hi"}}]}',
            'data: {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}',
            "data: [DONE]",
        ]
        with patch("chaos.llm.requests.post") as post:
            post.return_value = sse_response(lines)
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hi")
        self.assertEqual(
            reply.usage, {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        )

    def test_non_sse_fallback_parses_usage(self):
        usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
        with patch("chaos.llm.requests.post") as post:
            response = fake_response(payload=payload(content="hi", usage=usage))
            response.headers = {"Content-Type": "application/json"}
            post.return_value = response
            reply = chat_stream(base_url="https://x/v1", api_key="k", model="m", messages=[])
        self.assertEqual(reply.text, "hi")
        self.assertEqual(reply.usage, usage)


class AddUsageTest(unittest.TestCase):
    def test_sums_numeric_fields(self):
        merged = add_usage(
            {"prompt_tokens": 1, "total_tokens": 3},
            {"prompt_tokens": 2, "completion_tokens": 5, "total_tokens": 7},
        )
        self.assertEqual(merged, {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 10})

    def test_ignores_non_numeric_fields_and_none(self):
        self.assertEqual(add_usage({}, None), {})
        merged = add_usage(
            {"total_tokens": 1},
            {"total_tokens": 2, "prompt_tokens_details": {"cached_tokens": 4}, "cached": True},
        )
        self.assertEqual(merged, {"total_tokens": 3})


if __name__ == "__main__":
    unittest.main()
