from itertools import cycle

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static

from . import config as config_mod
from . import ui
from .agent import respond


def _hex_color(style_str, default):
    try:
        color = Style.parse(style_str).color
        if color is None:
            return default
        hex_value = color.get_truecolor().hex
        return hex_value if hex_value.startswith("#") else "#" + hex_value
    except Exception:
        return default


class ChaosApp(App):
    CSS = """
    #topbar { dock: top; height: auto; }
    #fire { width: auto; padding: 0 1; }
    #titles { width: 1fr; height: auto; }
    #log { height: 1fr; padding: 0 1; }
    #spinnerbar { dock: bottom; height: 1; }
    #spinnerlabel { width: auto; }
    #input { dock: bottom; }
    """

    BINDINGS = [("ctrl+q", "exit_app", "Quit")]

    def __init__(self, cfg, ref):
        super().__init__()
        self.cfg = cfg
        self.ref = ref
        self.ui_theme = config_mod.theme(cfg)
        self.messages = []
        self._spinner_on = False
        self._spinner_frames = cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(Text(ui.FIREBALL, style="bold red"), id="fire")
            with Vertical(id="titles"):
                yield Static(Text("CHAOS", style=self.ui_theme["banner"]), id="name")
                yield Static(f"model: {self.ref}", id="model")
                yield Static("hackathon agent harness · made by Team Chaos", id="tagline")
        yield RichLog(id="log")
        with Horizontal(id="spinnerbar"):
            yield Static(id="spinnerlabel")
        yield Input(placeholder="ask chaos…  (/model · /clear · /exit)", id="input")

    def on_mount(self):
        theme = self.ui_theme
        self.query_one("#name").styles.color = _hex_color(theme["banner"], "#ffaf00")
        self.query_one("#fire").styles.color = _hex_color("bold red", "#ff5f00")
        self.query_one("#model").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#tagline").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#input").styles.border = ("solid", _hex_color(theme["prompt"], "#00d7ff"))
        self.query_one("#spinnerbar").display = False
        self.query_one("#spinnerlabel").styles.color = _hex_color(theme["info"], "#888888")
        self.set_interval(0.08, self._tick_spinner)
        self.log_widget.write(ui.render_info(theme, "type a prompt — /model switch model · /clear reset · /exit quit"))
        self.query_one("#input", Input).focus()

    @property
    def log_widget(self):
        return self.query_one("#log", RichLog)

    def action_exit_app(self):
        self.exit()

    def _tick_spinner(self):
        if self._spinner_on:
            self.query_one("#spinnerlabel", Static).update(f"{next(self._spinner_frames)} thinking…")

    def _set_spinner(self, on):
        self._spinner_on = on
        self.query_one("#spinnerbar").display = on
        if on:
            self.query_one("#spinnerlabel", Static).update(f"{next(self._spinner_frames)} thinking…")

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if text in ("/exit", "/quit"):
            self.exit()
            return
        if text == "/clear":
            self.messages.clear()
            self.log_widget.clear()
            return
        if text == "/model" or text.startswith("/model "):
            arg = text.split(maxsplit=1)[1] if " " in text else ""
            self._model_command(arg)
            return
        self.messages.append({"role": "user", "content": text})
        self.log_widget.write(ui.render_user(self.ui_theme, text))
        self._set_spinner(True)
        self._ask()

    def _model_command(self, arg):
        if not arg:
            for m in config_mod.list_models(self.cfg):
                marker = "*" if m == self.ref else " "
                self.log_widget.write(ui.render_info(self.ui_theme, f"{marker} {m}"))
            return
        try:
            config_mod.resolve(self.cfg, arg)
        except config_mod.ConfigError as exc:
            self.log_widget.write(ui.render_error(self.ui_theme, exc))
            return
        self.ref = arg
        self.query_one("#model", Static).update(f"model: {arg}")
        self.log_widget.write(ui.render_info(self.ui_theme, f"switched to {arg}"))

    @work(thread=True)
    def _ask(self):
        try:
            reply = respond(self.cfg, self.ref, self.messages)
        except Exception as exc:
            self.call_from_thread(self._fail, exc)
            return
        self.call_from_thread(self._show_reply, reply)

    def _show_reply(self, reply):
        self._set_spinner(False)
        thinking = ui.render_thinking(self.ui_theme, reply.reasoning)
        if thinking is not None:
            self.log_widget.write(thinking)
        self.log_widget.write(ui.render_reply(self.ui_theme, reply.text))

    def _fail(self, exc):
        self._set_spinner(False)
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        self.log_widget.write(ui.render_error(self.ui_theme, exc))
