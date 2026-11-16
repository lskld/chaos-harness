from itertools import cycle

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, RichLog, SelectionList, Static
from textual.widgets.selection_list import Selection

from . import config as config_mod
from . import themes as themes_mod
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


class ThemePicker(ModalScreen):
    CSS = """
    ThemePicker { align: center middle; }
    #picker { width: 42; height: auto; max-height: 14; border: round; padding: 1 2; }
    """

    BINDINGS = [("escape", "dismiss"), Binding("enter", "pick", "Pick", priority=True)]

    def __init__(self, current, names, bg, accent):
        super().__init__()
        self._current = current
        self._names = names
        self._bg = bg
        self._accent = accent

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static("pick a theme — ↑/↓ + enter, esc to close", id="hint")
            yield SelectionList(
                *[Selection(name, name, name == self._current) for name in self._names],
                id="list",
            )

    def on_mount(self):
        picker = self.query_one("#picker")
        picker.styles.background = self._bg
        picker.styles.border = ("round", self._accent)
        self.query_one("#hint").styles.color = self._accent
        self.query_one("#list", SelectionList).focus()

    def on_selection_list_option_selected(self, event: SelectionList.OptionSelected):
        self.dismiss(event.option.value)

    def action_pick(self):
        selection_list = self.query_one("#list", SelectionList)
        if selection_list.highlighted is not None:
            self.dismiss(selection_list.options[selection_list.highlighted].value)


class ChaosApp(App):
    CSS = """
    #topbar { dock: top; height: auto; padding: 1 2 0 2; }
    #titles { width: 1fr; height: auto; }
    #right { width: 16; height: auto; }
    #mascot { height: 6; width: 16; text-align: right; }
    #status { height: 1; width: 16; text-align: right; padding: 0 1; }
    #log { height: 1fr; padding: 0 2; }
    #input { dock: bottom; margin: 0 2 1 2; }
    """

    BINDINGS = [("ctrl+q", "exit_app", "Quit")]

    def __init__(self, cfg, ref):
        super().__init__()
        self.cfg = cfg
        self.ref = ref
        self.theme_name = cfg.get("theme_name") or config_mod.DEFAULT_THEME_NAME
        self.ui_theme = config_mod.theme(cfg, self.theme_name)
        self.messages = []
        self._log_items = []
        self._spinner_on = False
        self._spinner_frames = cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self._mascot_up = False
        self._face_index = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            with Vertical(id="titles"):
                yield Static(Text("CHAOS", style=self.ui_theme["banner"]), id="name")
                yield Static(f"model: {self.ref}", id="model")
                yield Static("hackathon agent harness · made by Team Chaos", id="tagline")
                yield Static("type /help for the list of commands", id="helpline")
            with Vertical(id="right"):
                yield Static(ui.mascot_text(theme=self.ui_theme), id="mascot")
                yield Static("", id="status")
        yield RichLog(id="log")
        yield Input(placeholder="ask chaos…", id="input")

    def on_mount(self):
        self._apply_theme()
        self.set_interval(0.12, self._tick)
        self.query_one("#input", Input).focus()

    def _apply_theme(self):
        theme = self.ui_theme
        bg = _hex_color(theme["background"], "#1a0d0a")
        self.screen.styles.background = bg
        for widget in self.query("#topbar, #topbar *, #log, #input"):
            widget.styles.background = bg
        self.query_one("#name").styles.color = _hex_color(theme["banner"], "#ffaf00")
        self.query_one("#model").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#tagline").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#helpline").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#input").styles.border = ("solid", _hex_color(theme["prompt"], "#00d7ff"))
        self.query_one("#status").styles.color = _hex_color(theme["info"], "#888888")
        self.query_one("#mascot", Static).update(ui.mascot_text(theme=self.ui_theme))

    def _log(self, kind, payload):
        self._log_items.append((kind, payload))
        rendered = self._render_item(kind, payload)
        if rendered is not None:
            self.log_widget.write(rendered)

    def _render_item(self, kind, payload):
        theme = self.ui_theme
        renderers = {
            "user": lambda: ui.render_user(theme, payload),
            "thinking": lambda: ui.render_thinking(theme, payload),
            "reply": lambda: ui.render_reply(theme, payload),
            "info": lambda: ui.render_info(theme, payload),
            "error": lambda: ui.render_error(theme, payload),
        }
        return renderers[kind]()

    def _rebuild_log(self):
        self.log_widget.clear()
        for kind, payload in self._log_items:
            rendered = self._render_item(kind, payload)
            if rendered is not None:
                self.log_widget.write(rendered)

    @property
    def log_widget(self):
        return self.query_one("#log", RichLog)

    def action_exit_app(self):
        self.exit()

    def _tick(self):
        if not self._spinner_on:
            return
        self.query_one("#status", Static).update(f"{next(self._spinner_frames)} thinking…")
        face = ui.THINK_FACES[self._face_index % len(ui.THINK_FACES)]
        self._face_index += 1
        self._mascot_up = not self._mascot_up
        self.query_one("#mascot", Static).update(ui.mascot_text(face, up=self._mascot_up, theme=self.ui_theme))

    def _set_spinner(self, on):
        self._spinner_on = on
        if on:
            self._face_index = 0
            self._mascot_up = False
            self.query_one("#status", Static).update(f"{next(self._spinner_frames)} thinking…")
            self.query_one("#mascot", Static).update(ui.mascot_text(ui.THINK_FACES[0], theme=self.ui_theme))
        else:
            self.query_one("#status", Static).update("")
            self.query_one("#mascot", Static).update(ui.mascot_text(theme=self.ui_theme))

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
            self._log_items.clear()
            self.log_widget.clear()
            return
        if text == "/help":
            for line in (
                "/help — show this list",
                "/model [provider/model] — list or switch model",
                "/theme [name] — pick a color theme",
                "/clear — clear the chat",
                "/exit — quit (ctrl+q works too)",
            ):
                self._log("info", line)
            return
        if text == "/model" or text.startswith("/model "):
            arg = text.split(maxsplit=1)[1] if " " in text else ""
            self._model_command(arg)
            return
        if text == "/theme" or text.startswith("/theme "):
            arg = text.split(maxsplit=1)[1] if " " in text else ""
            self._theme_command(arg)
            return
        self.messages.append({"role": "user", "content": text})
        self._log("user", text)
        self._set_spinner(True)
        self._ask()

    def _model_command(self, arg):
        if not arg:
            for m in config_mod.list_models(self.cfg):
                marker = "*" if m == self.ref else " "
                self._log("info", f"{marker} {m}")
            return
        try:
            config_mod.resolve(self.cfg, arg)
        except config_mod.ConfigError as exc:
            self._log("error", exc)
            return
        self.ref = arg
        self.query_one("#model", Static).update(f"model: {arg}")
        self._log("info", f"switched to {arg}")

    def _theme_command(self, arg):
        if arg:
            self._switch_theme(arg)
            return
        theme = self.ui_theme
        self.push_screen(
            ThemePicker(
                self.theme_name,
                config_mod.theme_names(),
                _hex_color(theme["background"], "#1a0d0a"),
                _hex_color(theme["prompt"], "#ff87a2"),
            ),
            callback=self._switch_theme,
        )

    def _switch_theme(self, name):
        if not name:
            return
        if name not in themes_mod.THEMES:
            self._log("error", f"unknown theme {name!r}; available: {', '.join(config_mod.theme_names())}")
            return
        self.theme_name = name
        self.ui_theme = config_mod.theme(self.cfg, name)
        self._apply_theme()
        self._rebuild_log()

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
        if reply.reasoning:
            self._log("thinking", reply.reasoning)
        self._log("reply", reply.text)

    def _fail(self, exc):
        self._set_spinner(False)
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        self._log("error", exc)
