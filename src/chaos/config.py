import json
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".chaos" / "config.json"

DEFAULT_THEME = {
    "prompt": "bold cyan",
    "user": "bold white",
    "assistant": "green",
    "error": "bold red",
    "info": "dim",
}

EXAMPLE_CONFIG = {
    "default_model": "openrouter/auto",
    "providers": {
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-REPLACE_ME",
            "models": ["auto", "anthropic/claude-sonnet-4.5", "google/gemini-3-pro-preview"],
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_REPLACE_ME",
            "models": ["llama-3.3-70b-versatile"],
        },
    },
    "theme": DEFAULT_THEME,
}


class ConfigError(Exception):
    pass


def load(path=DEFAULT_CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
        raise ConfigError(
            f"no config found — wrote an example to {path}; add your API key and run again"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc


def theme(config):
    merged = dict(DEFAULT_THEME)
    merged.update(config.get("theme", {}))
    return merged


def list_models(config):
    return [
        f"{name}/{model}"
        for name, provider in config.get("providers", {}).items()
        for model in provider.get("models", [])
    ]


def resolve(config, ref):
    """Resolve a 'provider/model' reference to (base_url, api_key, model)."""
    if not ref:
        ref = config.get("default_model")
    if not ref:
        raise ConfigError("no model given and config has no default_model")
    provider_name, sep, model = ref.partition("/")
    if not sep or not model:
        available = ", ".join(list_models(config)) or "(none configured)"
        raise ConfigError(f"model must look like 'provider/model' (got {ref!r}); available: {available}")
    providers = config.get("providers", {})
    provider = providers.get(provider_name)
    if provider is None:
        configured = ", ".join(providers) or "(none)"
        raise ConfigError(f"unknown provider {provider_name!r}; configured: {configured}")
    try:
        return provider["base_url"], provider["api_key"], model
    except KeyError as exc:
        raise ConfigError(f"provider {provider_name!r} is missing {exc} in config") from exc
