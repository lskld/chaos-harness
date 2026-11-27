from . import commands
from . import config as config_mod


class Session:
    """Owns the conversation history and the mutable settings (model ref, theme,
    deadline) shared by both frontends (`cli.repl` and `ChaosApp`), so the semantics
    of slash commands live here exactly once.

    `handle_command(name, arg)` runs a slash command and returns (action, out_events):
    out_events are renderable (kind, text) pairs, and action is a frontend hook —
    "exit", "clear", "pick_model", "pick_theme" — or None when out_events alone carry
    the result. Settings changes are persisted to config_path when one is set.
    """

    def __init__(self, cfg, ref, config_path=None):
        self.cfg = dict(cfg)
        self.ref = ref
        self.config_path = config_path
        self.theme_name = cfg.get("theme_name") or config_mod.DEFAULT_THEME_NAME
        self.messages = []

    @property
    def theme(self):
        return config_mod.theme(self.cfg, self.theme_name)

    def _persist(self, out, what):
        if self.config_path is None:
            return
        try:
            config_mod.save(self.config_path, self.cfg)
        except OSError as exc:
            out.append(("error", f"could not save {what} to config: {exc}"))

    def clear(self):
        self.messages.clear()
        return [("info", "history cleared")]

    def model_options(self):
        return config_mod.list_models(self.cfg)

    def list_models(self):
        _, out = commands.model_command(self.cfg, "", self.ref)
        return out

    def list_themes(self):
        _, out = commands.theme_command("", self.theme_name)
        return out

    def switch_model(self, arg):
        new_ref, out = commands.model_command(self.cfg, arg, self.ref)
        if new_ref != self.ref:
            self.ref = new_ref
            self.cfg["default_model"] = new_ref
            self._persist(out, "model")
        return out

    def switch_theme(self, arg):
        new_name, out = commands.theme_command(arg, self.theme_name)
        if new_name:
            self.theme_name = new_name
            self.cfg["theme_name"] = new_name
            self._persist(out, "theme")
        return out

    def set_deadline(self, arg):
        value, out = commands.deadline_command(arg)
        if value is commands.UNCHANGED:
            return out
        if value is None:
            self.cfg.pop("deadline", None)
        else:
            self.cfg["deadline"] = value
        self._persist(out, "deadline")
        return out

    def handle_command(self, name, arg):
        if name in ("/exit", "/quit"):
            return "exit", []
        if name == "/help":
            return None, [("info", line) for line in commands.HELP_LINES]
        if name == "/clear":
            return "clear", self.clear()
        if name == "/model":
            if not arg:
                return "pick_model", []
            return None, self.switch_model(arg)
        if name == "/theme":
            if not arg:
                return "pick_theme", []
            return None, self.switch_theme(arg)
        if name == "/deadline":
            return None, self.set_deadline(arg)
        return None, []
