import requests


class LLMError(Exception):
    pass


def chat(*, base_url, api_key, model, messages, timeout=120):
    """One OpenAI-compatible chat completion call; returns the assistant text."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMError(f"request to {url} failed: {exc}") from exc
    if response.status_code != 200:
        raise LLMError(f"API error {response.status_code} from {url}: {response.text[:300]}")
    try:
        message = response.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"unexpected response from {url}: {exc}") from exc
    return _content_text(message.get("content"))


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
