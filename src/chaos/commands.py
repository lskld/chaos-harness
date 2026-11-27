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

COMMAND_ALIASES = {"/quit": "/exit"}


def _parse_help_lines():
    """name -> (arg_hint, description), parsed from HELP_LINES so the two never drift."""
    entries = {}
    for line in HELP_LINES:
        name, _, rest = line.partition(" ")
        hint = ""
        if rest.startswith("["):
            end = rest.find("]")
            hint = rest[: end + 1]
            rest = rest[end + 1 :].strip()
        description = rest.split("—", 1)[1].strip() if "—" in rest else rest.strip()
        entries[name] = (hint, description)
    for alias, target in COMMAND_ALIASES.items():
        if target in entries:
            entries.setdefault(alias, entries[target])
    return entries


HELP_ENTRIES = _parse_help_lines()


def arg_hint(name):
    """The bracketed argument hint of a command from its help line ('' when it takes none)."""
    return HELP_ENTRIES.get(name, ("", ""))[0]


def description(name):
    """The short description of a command from its help line."""
    return HELP_ENTRIES.get(name, ("", ""))[1]


def _arg_options(name, cfg):
    if name == "/theme":
        return config_mod.theme_names()
    if name == "/model":
        return config_mod.list_models(cfg) if cfg is not None else []
    if name == "/deadline":
        return ["off"]
    return []


def suggestions(line, cfg=None):
    """Completion candidates for an input line: (stage, [(value, description), ...]).

    stage is "command" while the line is a bare slash prefix (no space yet),
    "arg" while completing the argument of a command that takes one, and None
    when there is nothing to complete.
    """
    if not line.startswith("/"):
        return None, []
    if " " not in line:
        return "command", [(name, description(name)) for name in COMMANDS if name.startswith(line)]
    name, arg = split(line)
    if name not in COMMANDS or not arg_hint(name):
        return None, []
    return "arg", [(option, "") for option in _arg_options(name, cfg) if option.startswith(arg)]


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
