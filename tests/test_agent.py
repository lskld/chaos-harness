import unittest
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


if __name__ == "__main__":
    unittest.main()
