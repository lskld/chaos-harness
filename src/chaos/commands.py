from . import config as config_mod

COMMANDS = ("/exit", "/quit", "/help", "/clear", "/model", "/theme", "/deadline")

HELP_LINES = (
    "/help — show this list",
    "/model [provider/model] — pick or switch model",
    "/theme [name] — pick a color theme",
    "/deadline [HH:MM|off] — set or clear the hackathon countdown",
    "/clear — clear the chat",
    "/exit — quit",
)

UNCHANGED = object()


def split(line):
    """Split an input line into (command, arg); (None, '') when it is plain text."""
    command = line.strip()
    if not command.startswith("/"):
        return None, ""
    name, _, arg = command.partition(" ")
    return name, arg.strip()


def model_command(cfg, arg, current):
    """List models (no arg) or switch model; returns (ref, [(kind, text), ...])."""
    if not arg:
        out = [("info", f"{'*' if m == current else ' '} {m}") for m in config_mod.list_models(cfg)]
        return current, out
    try:
        config_mod.resolve(cfg, arg)
    except config_mod.ConfigError as exc:
        return current, [("error", str(exc))]
    return arg, [("info", f"switched to {arg}")]


def theme_command(arg, current=None):
    """List themes (no arg) or validate a theme name; returns (name or None, [(kind, text), ...])."""
    names = config_mod.theme_names()
    if not arg:
        out = [("info", f"{'*' if n == current else ' '} {n}") for n in names]
        return None, out
    if arg not in names:
        return None, [("error", f"unknown theme {arg!r}; available: {', '.join(names)}")]
    return arg, []


def deadline_command(arg, now=None):
    """Parse a /deadline arg; returns (value, [(kind, text), ...]) where value is
    the new ISO deadline, None to clear, or UNCHANGED when the arg is invalid."""
    try:
        value = config_mod.resolve_deadline(arg, now=now)
    except config_mod.ConfigError as exc:
        return UNCHANGED, [("error", str(exc))]
    if value is None:
        return None, [("info", "deadline cleared")]
    remaining = config_mod.deadline_remaining(value, now)
    return value, [("info", f"deadline set to {value} — {config_mod.format_remaining(remaining)} left")]
