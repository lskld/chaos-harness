from . import config as config_mod

COMMANDS = ("/exit", "/quit", "/help", "/clear", "/model", "/theme")

HELP_LINES = (
    "/help — show this list",
    "/model [provider/model] — pick or switch model",
    "/theme [name] — pick a color theme",
    "/clear — clear the chat",
    "/exit — quit",
)


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
