import json
from typing import NamedTuple

import requests

from . import config as config_mod


class LLMError(Exception):
    pass


class Reply(NamedTuple):
    text: str
    reasoning: str = ""
    tool_calls: tuple = ()
    events: tuple = ()


def chat(*, base_url, api_key, model, messages, tools=None, timeout=120):
    """One OpenAI-compatible chat completion call; returns the assistant text and any tool calls."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMError(
            config_mod.redact(f"request to {url} failed: {type(exc).__name__}: {str(exc)[:200]}", (api_key,))
        ) from exc
    if response.status_code != 200:
        raise LLMError(
            config_mod.redact(f"API error {response.status_code} from {url}: {response.text[:300]}", (api_key,))
        )
    try:
        message = response.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(
            config_mod.redact(f"unexpected response from {url}: {exc}", (api_key,))
        ) from exc
    return Reply(
        text=_content_text(message.get("content")),
        reasoning=_reasoning_text(message),
        tool_calls=_tool_calls(message),
    )


def chat_stream(*, base_url, api_key, model, messages, tools=None, timeout=120, on_delta=None, max_tokens=None):
    """Streaming variant of chat(): parses SSE chunks and calls on_delta(field, text) for each
    streamed chunk (field is "content" or "reasoning"); returns the accumulated Reply.

    If the API answers with a plain (non-SSE) completion, it is parsed like chat().
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
    except requests.RequestException as exc:
        raise LLMError(
            config_mod.redact(f"request to {url} failed: {type(exc).__name__}: {str(exc)[:200]}", (api_key,))
        ) from exc
    if response.status_code != 200:
        raise LLMError(
            config_mod.redact(f"API error {response.status_code} from {url}: {response.text[:300]}", (api_key,))
        )
    if "text/event-stream" not in response.headers.get("Content-Type", ""):
        try:
            message = response.json()["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(
            config_mod.redact(f"unexpected response from {url}: {exc}", (api_key,))
        ) from exc
        return Reply(
            text=_content_text(message.get("content")),
            reasoning=_reasoning_text(message),
            tool_calls=_tool_calls(message),
        )
    content_parts = []
    reasoning_parts = []
    calls = {}
    id_aliases = {}
    fresh_key = -1
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            delta = json.loads(data)["choices"][0]["delta"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            continue
        content = delta.get("content")
        if isinstance(content, str) and content:
            content_parts.append(content)
            if on_delta is not None:
                on_delta("content", content)
        elif isinstance(content, list):
            text = _content_text(content)
            if text:
                content_parts.append(text)
                if on_delta is not None:
                    on_delta("content", text)
        reasoning = delta.get("reasoning") or delta.get("reasoning_content") or delta.get("thinking")
        if isinstance(reasoning, str) and reasoning:
            reasoning_parts.append(reasoning)
            if on_delta is not None:
                on_delta("reasoning", reasoning)
        for call in delta.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            index = call.get("index")
            if call_id and index is not None:
                id_aliases[call_id] = ("index", index)
                if ("id", call_id) in calls and ("index", index) not in calls:
                    calls[("index", index)] = calls.pop(("id", call_id))
            if index is not None:
                key = ("index", index)
            elif call_id:
                key = id_aliases.get(call_id, ("id", call_id))
            else:
                key = ("fresh", fresh_key)
                fresh_key -= 1
            entry = calls.setdefault(
                key,
                {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
            )
            if call.get("id"):
                entry["id"] = call["id"]
            function = call.get("function") or {}
            if function.get("name"):
                entry["function"]["name"] = function["name"]
            if function.get("arguments"):
                entry["function"]["arguments"] += function["arguments"]
    return Reply(
        text="".join(content_parts),
        reasoning="".join(reasoning_parts),
        tool_calls=tuple(calls.values()),
    )


def _tool_calls(message):
    """Normalize tool_calls to the canonical spec shape ({id, type, function: {name, arguments}}),
    so echoing them back into the history is accepted by strictly-validating APIs."""
    calls = message.get("tool_calls") or []
    parsed = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        arguments = function.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        parsed.append(
            {
                "id": call.get("id") or "",
                "type": "function",
                "function": {"name": function.get("name") or "", "arguments": arguments},
            }
        )
    return tuple(parsed)


def _reasoning_text(message):
    reasoning = (
        message.get("reasoning") or message.get("reasoning_content") or message.get("thinking") or ""
    )
    return reasoning if isinstance(reasoning, str) else ""


def _content_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text":
                texts.append(part.get("text", ""))
        return "".join(texts)
    raise LLMError(f"unsupported content type: {type(content).__name__}")
