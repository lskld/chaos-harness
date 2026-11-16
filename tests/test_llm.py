import unittest
from unittest.mock import Mock, patch

import requests

from chaos.llm import LLMError, chat


def fake_response(status=200, payload=None, text=""):
    response = Mock()
    response.status_code = status
    response.json = lambda: payload
    response.text = text
    return response


def payload(content=None, reasoning=None, extra_message=None):
    message = {"content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    if extra_message:
        message.update(extra_message)
    return {"choices": [{"message": message}]}


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


if __name__ == "__main__":
    unittest.main()
