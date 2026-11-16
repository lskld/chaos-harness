import unittest
from unittest.mock import Mock, patch

import requests

from chaos.llm import LLMError, chat

OK_PAYLOAD = {"choices": [{"message": {"content": "hello there"}}]}


def fake_response(status=200, payload=None, text=""):
    response = Mock()
    response.status_code = status
    response.json = lambda: payload
    response.text = text
    return response


class ChatTest(unittest.TestCase):
    def test_posts_openai_compatible_payload(self):
        with patch("chaos.llm.requests.post") as post:
            post.return_value = fake_response(payload=OK_PAYLOAD)
            reply = chat(
                base_url="https://api.example.com/v1/",
                api_key="sk-test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        self.assertEqual(reply, "hello there")
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


if __name__ == "__main__":
    unittest.main()
