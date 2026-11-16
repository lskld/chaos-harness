from . import config as config_mod
from .llm import chat


def respond(cfg, ref, messages):
    """One agent turn: call the model, append its reply to messages, return it."""
    base_url, api_key, model = config_mod.resolve(cfg, ref)
    reply = chat(base_url=base_url, api_key=api_key, model=model, messages=messages)
    messages.append({"role": "assistant", "content": reply.text})
    return reply
