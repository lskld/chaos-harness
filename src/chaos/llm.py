import json
from typing import NamedTuple

import requests


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
        raise LLMError(f"request to {url} failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
    if response.status_code != 200:
        raise LLMError(f"API error {response.status_code} from {url}: {response.text[:300]}")
    try:
        message = response.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"unexpected response from {url}: {exc}") from exc
    return Reply(
        text=_content_text(message.get("content")),
        reasoning=_reasoning_text(message),
        tool_calls=_tool_calls(message),
    )


def _tool_calls(message):
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
                "name": function.get("name") or "",
                "arguments": arguments,
            }
        )
    return tuple(parsed)


def _reasoning_text(message):
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
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
