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
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"unexpected response from {url}: {exc}") from exc
