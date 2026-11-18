import json
import os
import stat
from pathlib import Path

from .themes import DEFAULT_THEME_NAME, THEMES

DEFAULT_CONFIG_PATH = Path.home() / ".chaos" / "config.json"

DEFAULT_THEME = THEMES[DEFAULT_THEME_NAME]

EXAMPLE_CONFIG = {
    "default_model": "",
    "providers": {
        "my-provider": {
            "base_url": "",
            "api_key": "",
            "models": [],
        }
    },
    "theme": DEFAULT_THEME,
}


class ConfigError(Exception):
    pass


def _write_private(path, text):
    """Write the config so only the owner can read it — it holds API keys."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)


def _tighten_permissions(path):
    try:
        if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
            os.chmod(path, 0o600)
    except OSError:
        pass


def load(path=DEFAULT_CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_private(path, json.dumps(EXAMPLE_CONFIG, indent=2) + "\n")
        raise ConfigError(
            f"no config found — wrote an example to {path}; fill in a provider, then run again"
        )
    _tighten_permissions(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc


def save(path, config):
    path = Path(path)
    _write_private(path, json.dumps(config, indent=2) + "\n")


def theme(config, name=None):
    base = THEMES.get(name or config.get("theme_name") or DEFAULT_THEME_NAME, DEFAULT_THEME)
    merged = dict(base)
    merged.update(config.get("theme", {}))
    return merged


def theme_names():
    return list(THEMES)


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


REDACTED = "***redacted***"
SECRET_KEYS = ("api_key", "api_secret", "access_token")
MIN_SECRET_LENGTH = 8


def secrets(config):
    """All configured secret values (provider API keys, future search keys, ...)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in SECRET_KEYS and isinstance(value, str) and value:
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(config)
    return tuple(dict.fromkeys(found))


def redact(text, secrets):
    """Replace secret values in text. Very short values are skipped so a weak
    key can't mangle all output."""
    for secret in secrets:
        if len(secret) >= MIN_SECRET_LENGTH:
            text = text.replace(secret, REDACTED)
    return text
