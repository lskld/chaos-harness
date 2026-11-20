import json
import os
import re
import stat
from datetime import datetime, timedelta
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
    "theme_name": DEFAULT_THEME_NAME,
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
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_private(path, json.dumps(EXAMPLE_CONFIG, indent=2) + "\n")
        except OSError as exc:
            raise ConfigError(
                f"cannot write example config to {path}: {exc} — check that the directory is writable"
            ) from exc
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


DEADLINE_USAGE = "deadline must be HH:MM, HH:MM:SS, or off"


def resolve_deadline(arg, now=None):
    """Resolve a /deadline arg to an absolute ISO-8601 timestamp with the local
    UTC offset: the next occurrence of HH:MM[:SS] local time (today if still
    ahead, otherwise tomorrow). 'off'/'clear' -> None; anything else raises
    ConfigError naming the expected format."""
    arg = (arg or "").strip()
    if arg.lower() in ("off", "clear"):
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", arg)
    if match:
        hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
        if hour > 23 or minute > 59 or second > 59:
            match = None
    if not match:
        raise ConfigError(f"{DEADLINE_USAGE} (got {arg!r})")
    if now is None:
        now = datetime.now()
    elif now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    candidate = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.astimezone().isoformat(timespec="seconds")


def parse_deadline(value):
    """An ISO deadline string as an aware datetime; None when unset/unparseable."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _now_aware(now):
    if now is None:
        return datetime.now().astimezone()
    return now if now.tzinfo is not None else now.astimezone()


def deadline_remaining(value, now=None):
    """Seconds until an ISO deadline (<= 0 when expired); None when unparseable."""
    deadline = parse_deadline(value)
    if deadline is None:
        return None
    return (deadline - _now_aware(now)).total_seconds()


def format_remaining(total_seconds):
    """Floor total seconds to 'H:MM' (hours not zero-padded)."""
    hours, rem = divmod(int(total_seconds), 3600)
    return f"{hours}:{rem // 60:02d}"


def deadline_text(cfg, now=None):
    """The top-bar countdown '⏳ H:MM left'; '' when unset, invalid, or expired."""
    remaining = deadline_remaining(cfg.get("deadline"), now)
    if remaining is None or remaining <= 0:
        return ""
    return f"⏳ {format_remaining(remaining)} left"


def deadline_context(cfg, now=None):
    """The system-prompt deadline line; '' when unset, invalid, or expired."""
    deadline = parse_deadline(cfg.get("deadline"))
    remaining = deadline_remaining(cfg.get("deadline"), now)
    if deadline is None or remaining is None or remaining <= 0:
        return ""
    return (
        f"Hackathon deadline: {deadline.isoformat(timespec='seconds')} — "
        f"{format_remaining(remaining)} remaining. Factor the remaining time into your "
        "decisions: when little time is left, prioritize a shippable demo over polish/refactors."
    )
