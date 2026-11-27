import os
from itertools import cycle

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Collapsible, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

from . import commands
from . import config as config_mod
from . import tools as tools_mod
from . import ui
from .agent import respond, rollback_turn


def _hex_color(style_str, default):
    try:
        color = Style.parse(style_str).color
        if color is None:
            return default
        hex_value = color.get_truecolor().hex
        return hex_value if hex_value.startswith("#") else "#" + hex_value
    except Exception:
        return default


_RENDERERS = {
    "user": ui.render_user,
    "thinking": ui.render_thinking,
    "tool": ui.render_tool,
    "reply": ui.render_reply,
    "info": ui.render_info,
    "error": ui.render_error,
    "ask_user": ui.render_ask_user,
}


class ListPicker(ModalScreen):
    CSS = """
    #picker { width: 42; height: auto; max-height: 14; border: round; padding: 1 2; }
    """

    BINDINGS = [("escape", "dismiss"), Binding("enter", "pick", "Pick", priority=True)]

    def __init__(self, current, options, bg, accent, hint):
        super().__init__()
        self.styles.align = ("center", "middle")
        self._current = current
        self._options = options
        self._bg = bg
        self._accent = accent
        self._hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static(self._hint, id="hint")
            yield SelectionList(
                *[Selection(option, option, option == self._current) for option in self._options],
                id="list",
            )

    def on_mount(self):
        picker = self.query_one("#picker")
        picker.styles.background = self._bg
        picker.styles.border = ("round", self._accent)
        self.query_one("#hint").styles.color = self._accent
        self.query_one("#list", SelectionList).focus()

    def action_pick(self):
        selection_list = self.query_one("#list", SelectionList)
        if selection_list.highlighted is not None:
            self.dismiss(selection_list.options[selection_list.highlighted].value)

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        selection_list = event.selection_list
        if event.selection.value in selection_list.selected:
            selection_list.deselect_all()
            selection_list.select(event.selection.value)


class ThemePicker(ListPicker):
    def __init__(self, current, names, bg, accent):
        super().__init__(current, names, bg, accent, "pick a theme — ↑/↓ + enter, esc to close")


class ModelPicker(ListPicker):
    def __init__(self, current, models, bg, accent):
        super().__init__(current, models, bg, accent, "pick a model — ↑/↓ + enter, esc to close")


class ThoughtProcess(Collapsible):
    """One turn's live event stream behind a collapsed 'thought process' dropdown."""

    MAX_BLOCKS = 400

    def __init__(self, theme, events):
        log = VerticalScroll(classes="process-log")
        log.styles.color = _hex_color(theme["thinking"], "#c4a3a3")
        title = Text("thought process", style=theme["thinking"])
        super().__init__(log, title=title, collapsed=True, classes="process")
        self.events = events
        self._log = log
        self._live = {}
        self._pending = []
        self._pending_tools = []
        for event in events:
            self._write_event(theme, event)

    def on_mount(self):
        for block in self._pending:
            self._log.mount(block)
        self._pending.clear()
        while len(self._log.children) > self.MAX_BLOCKS:
            self._log.children[0].remove()

    def add_event(self, theme, event):
        self.events.append(event)
        self._write_event(theme, event)

    def _write_event(self, theme, event):
        kind = event.get("type")
        if kind == "delta":
            self._append_delta(theme, event.get("field", ""), event.get("text", ""))
            return
        if kind == "reply":
            block = self._live.pop("content", None)
            if block is not None:
                self._discard_block(block)
        self._live = {}
        if kind == "tool_call":
            block = Static(ui.render_tool_call(theme, event))
            self._pending_tools.append(block)
            self._mount_block(block)
            return
        if kind == "tool_result" and self._pending_tools:
            self._pending_tools.pop(0).update(ui.render_tool(theme, event))
            return
        rendered = ui.render_event(theme, event)
        if rendered is not None:
            self._mount_block(rendered)

    def _append_delta(self, theme, field, text):
        if field not in ("reasoning", "content") or not text:
            return
        if field not in self._live:
            if field == "reasoning":
                self._mount_block(Static(Text("thinking", style=theme["thinking"])))
            self._live[field] = Static(Text("", style=theme["thinking"]))
            self._mount_block(self._live[field])
        body = self._live[field].content
        body.append(text)
        self._live[field].update(body)

    def _discard_block(self, block):
        if block in self._pending:
            self._pending.remove(block)
        elif block.is_mounted:
            block.remove()

    def _mount_block(self, renderable):
        block = renderable if isinstance(renderable, Static) else Static(renderable)
        if self._log.is_mounted:
            self._log.mount(block)
            if len(self._log.children) > self.MAX_BLOCKS:
                self._log.children[0].remove()
        else:
            self._pending.append(block)


class CommandInput(Input):
    """The chat input; while slash-command suggestions are visible, arrows move the
    highlight, tab accepts it and escape dismisses the list."""

    BINDINGS = [
        Binding("up", "suggestion_up", show=False, priority=True),
        Binding("down", "suggestion_down", show=False, priority=True),
        Binding("tab", "suggestion_accept", show=False, priority=True),
        Binding("escape", "suggestion_dismiss", show=False, priority=True),
    ]

    def action_suggestion_up(self) -> None:
        self.app._move_suggestion(-1)

    def action_suggestion_down(self) -> None:
        self.app._move_suggestion(1)

    def action_suggestion_accept(self) -> None:
        if not self.app._accept_suggestion():
            self.screen.focus_next()

    def action_suggestion_dismiss(self) -> None:
        self.app._dismiss_suggestions()


class ChaosApp(App):
    CSS = """
    #topbar { dock: top; height: auto; padding: 1 2 0 2; }
    #titles { width: 1fr; height: auto; }
    #right { width: 16; height: auto; }
    #mascot { height: 6; width: 16; text-align: right; }
    #status { height: 1; width: 16; text-align: right; padding: 0 1; }
    #deadline { height: 1; width: 16; text-align: right; padding: 0 1; }
    #log { height: 1fr; padding: 0 2; }
    .process { margin: 0 0 0 1; border-top: none; }
    .process, .process:focus-within, .process *, .process *:hover, .process *:focus, .process *:focus-within {
        background: transparent;
    }
    .process-log { height: auto; max-height: 20; padding: 0 0 0 2; }
    #bottom { dock: bottom; height: auto; }
    #suggestions { display: none; height: auto; max-height: 8; padding: 0 2; margin: 0 2; }
    #input { margin: 0 2; }
    #statusline { height: 1; }
    #cwd { height: 1; width: 1fr; padding: 0 2; }
    #usage { height: 1; width: auto; text-align: right; padding: 0 2; }
    """

    BINDINGS = [("ctrl+q", "exit_app", "Quit")]

    def __init__(self, cfg, ref, config_path=None):
        super().__init__()
        self.cfg = dict(cfg)
        self.ref = ref
        self.config_path = config_path
        self.theme_name = cfg.get("theme_name") or config_mod.DEFAULT_THEME_NAME
        self.ui_theme = config_mod.theme(cfg, self.theme_name)
        self.messages = []
        self.workspace_root = tools_mod.workspace_root(cfg)
        self._log_items = []
        self._spinner_on = False
        self._spinner_frames = cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self._mascot_up = False
        self._face_index = 0
        self._deadline_widget = None
        self._pending_ask = None
        self._busy = False
        self._queued_inputs = []
        self._suggestion_stage = None
        self._suggestion_items = []
        self._suggestion_index = 0
        self._turn_usage = {}
        self._session_tokens = 0

    def _cwd_text(self):
        root = str(self.workspace_root)
        home = os.path.expanduser("~")
        if root == home:
            return "~"
        if root.startswith(home + os.sep):
            return "~" + root[len(home):]
        return root

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            with Vertical(id="titles"):
                yield Static(Text(ui.NAME, style=self.ui_theme["banner"]), id="name")
                yield Static(f"model: {self.ref}", id="model")
                yield Static(ui.TAGLINE, id="tagline")
                yield Static(ui.HELP_HINT, id="helpline")
            with Vertical(id="right"):
                yield Static(ui.mascot_text(theme=self.ui_theme), id="mascot")
                yield Static("", id="status")
                yield Static("", id="deadline")
        yield VerticalScroll(id="log")
        with Vertical(id="bottom"):
            yield Static("", id="suggestions")
            yield CommandInput(placeholder="ask chaos…", id="input")
            with Horizontal(id="statusline"):
                yield Static(Text(self._cwd_text()), id="cwd")
                yield Static("", id="usage")

    def on_mount(self):
        self._apply_theme()
        self._deadline_widget = self.query_one("#deadline", Static)
        self._update_deadline()
        self.set_interval(0.12, self._tick)
        self.query_one("#input", Input).focus()
        warning = tools_mod.root_warning(
            self.workspace_root, self.config_path or str(config_mod.DEFAULT_CONFIG_PATH)
        )
        if warning:
            self._log("error", f"warning: {warning}")

    def _apply_theme(self):
        theme = self.ui_theme
        bg = _hex_color(theme["background"], "#1a0d0a")
        info = _hex_color(theme["info"], "#888888")
        self.screen.styles.background = bg
        for widget in self.query("#topbar, #topbar *, #log, #log *, #bottom, #bottom *"):
            widget.styles.background = bg
        self.query_one("#name").styles.color = _hex_color(theme["banner"], "#ffaf00")
        for widget in self.query("#model, #usage, #tagline, #helpline, #status, #deadline, #cwd"):
            widget.styles.color = info
        self.query_one("#input").styles.border = ("solid", _hex_color(theme["prompt"], "#00d7ff"))
        self.query_one("#mascot", Static).update(ui.mascot_text(theme=theme))
        self._update_suggestions()

    def _log(self, kind, payload):
        self._log_items.append((kind, payload))
        return self._mount_item(kind, payload)

    def _render_item(self, kind, payload):
        return _RENDERERS[kind](self.ui_theme, payload)

    def _mount_item(self, kind, payload):
        if kind == "process":
            widget = ThoughtProcess(self.ui_theme, payload)
            self.log_widget.mount(widget)
        else:
            rendered = self._render_item(kind, payload)
            widget = Static(rendered) if rendered is not None else None
            if widget is not None:
                self.log_widget.mount(widget)
        self.log_widget.scroll_end(animate=False)
        return widget

    def _rebuild_log(self):
        self.log_widget.remove_children()
        for kind, payload in self._log_items:
            self._mount_item(kind, payload)

    @property
    def log_widget(self):
        return self.query_one("#log", VerticalScroll)

    def _quit(self):
        self._release_pending_ask(RuntimeError("session ended while waiting for an answer"))
        self.exit()

    def action_exit_app(self):
        self._quit()

    def _release_pending_ask(self, error=None):
        """Resolve a still-pending ask future so a worker blocked in future.result()
        is never left hanging; error=None resolves with an empty answer."""
        pending, self._pending_ask = self._pending_ask, None
        if pending is None:
            return
        future = pending.get("future")
        if future is None or future.done():
            return
        if error is None:
            future.set_result("")
        else:
            future.set_exception(error)

    def _update_deadline(self):
        if self._deadline_widget is not None and self._deadline_widget.is_mounted:
            self._deadline_widget.update(config_mod.deadline_text(self.cfg))

    def _update_usage(self):
        widget = self.query_one("#usage", Static)
        if widget.is_mounted:
            widget.update(ui.usage_text(self._turn_usage, self._session_tokens))

    def _tick(self):
        self._update_deadline()
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

    def on_input_changed(self, event: Input.Changed):
        if event.input.id != "input":
            return
        self._update_suggestions()

    def _update_suggestions(self):
        value = self.query_one("#input", Input).value
        stage, items = commands.suggestions(value, self.cfg)
        self._suggestion_stage = stage
        self._suggestion_items = items
        self._suggestion_index = 0
        widget = self.query_one("#suggestions", Static)
        widget.display = bool(items)
        if items:
            widget.update(self._render_suggestions())

    def _render_suggestions(self):
        theme = self.ui_theme
        text = Text()
        for index, (value, desc) in enumerate(self._suggestion_items):
            if index:
                text.append("\n")
            highlighted = index == self._suggestion_index
            style = theme["prompt"] if highlighted else theme["info"]
            text.append("❯ " if highlighted else "  ", style=style)
            text.append(value, style=style if highlighted else "")
            if desc:
                text.append(f"  {desc}", style=theme["info"])
        return text

    def _move_suggestion(self, delta):
        if not self._suggestion_items:
            return False
        self._suggestion_index = (self._suggestion_index + delta) % len(self._suggestion_items)
        self.query_one("#suggestions", Static).update(self._render_suggestions())
        return True

    def _accept_suggestion(self):
        if not self._suggestion_items:
            return False
        value, _ = self._suggestion_items[self._suggestion_index % len(self._suggestion_items)]
        input_widget = self.query_one("#input", Input)
        if self._suggestion_stage == "command":
            new_value = value + (" " if commands.arg_hint(value) else "")
        else:
            name, _ = commands.split(input_widget.value)
            new_value = f"{name} {value}"
        input_widget.value = new_value
        input_widget.cursor_position = len(new_value)
        return True

    def _dismiss_suggestions(self):
        self._suggestion_stage = None
        self._suggestion_items = []
        self._suggestion_index = 0
        self.query_one("#suggestions", Static).display = False

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if (
            self._suggestion_stage == "command"
            and self._suggestion_items
            and text not in commands.COMMANDS
        ):
            self._accept_suggestion()
            return
        event.input.clear()
        if not text:
            return
        name, arg = commands.split(text)
        if name in commands.COMMANDS:
            self._dispatch_command(name, arg)
            return
        if self._pending_ask is not None:
            pending, self._pending_ask = self._pending_ask, None
            self._log("user", text)
            future = pending.get("future")
            if future is not None and not future.done():
                future.set_result(text)
            return
        self._submit(text)

    def _submit(self, text):
        if self._busy:
            self._queued_inputs.append(text)
            self._log("info", "still thinking — your message is queued")
            return
        self._busy = True
        self.messages.append({"role": "user", "content": text})
        self._log("user", text)
        self._set_spinner(True)
        process = self._log("process", [])
        self._ask(process)

    def _finish_turn(self):
        self._busy = False
        if self._queued_inputs:
            self._submit(self._queued_inputs.pop(0))

    def _dispatch_command(self, name, arg):
        if name in ("/exit", "/quit"):
            self._quit()
        elif name == "/help":
            for line in commands.HELP_LINES:
                self._log("info", line)
        elif name == "/clear":
            self.messages.clear()
            self._log_items.clear()
            self.log_widget.remove_children()
        elif name == "/model":
            self._model_command(arg)
        elif name == "/theme":
            self._theme_command(arg)
        elif name == "/deadline":
            self._deadline_command(arg)

    def _model_command(self, arg):
        if arg:
            self._switch_model(arg)
            return
        models = config_mod.list_models(self.cfg)
        if not models:
            self._log("error", "no models configured — add some under providers in config.json")
            return
        theme = self.ui_theme
        self.push_screen(
            ModelPicker(
                self.ref,
                models,
                _hex_color(theme["background"], "#1a0d0a"),
                _hex_color(theme["prompt"], "#ff87a2"),
            ),
            callback=self._switch_model,
        )

    def _switch_model(self, ref):
        if not ref:
            return
        current = self.ref
        self.ref, out = commands.model_command(self.cfg, ref, self.ref)
        for kind, payload in out:
            self._log(kind, payload)
        if self.ref != current:
            self.query_one("#model", Static).update(f"model: {self.ref}")
            if self.config_path is not None:
                self.cfg["default_model"] = self.ref
                try:
                    config_mod.save(self.config_path, self.cfg)
                except OSError as exc:
                    self._log("error", f"could not save model to config: {exc}")

    def _deadline_command(self, arg):
        value, out = commands.deadline_command(arg)
        for kind, payload in out:
            self._log(kind, payload)
        if value is commands.UNCHANGED:
            return
        if value is None:
            self.cfg.pop("deadline", None)
        else:
            self.cfg["deadline"] = value
        if self.config_path is not None:
            try:
                config_mod.save(self.config_path, self.cfg)
            except OSError as exc:
                self._log("error", f"could not save deadline to config: {exc}")
        self._update_deadline()

    def _theme_command(self, arg):
        if not arg:
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
            return
        new_name, out = commands.theme_command(arg, self.theme_name)
        for kind, payload in out:
            self._log(kind, payload)
        if new_name:
            self._switch_theme(new_name)

    def _switch_theme(self, name):
        if not name:
            return
        self.theme_name = name
        self.ui_theme = config_mod.theme(self.cfg, name)
        self._apply_theme()
        self._rebuild_log()
        if self.config_path is not None:
            self.cfg["theme_name"] = name
            try:
                config_mod.save(self.config_path, self.cfg)
            except OSError as exc:
                self._log("error", f"could not save theme to config: {exc}")

    @work(thread=True)
    def _ask(self, process):
        def on_event(event):
            self.call_from_thread(self._add_process_event, process, event)

        try:
            reply = respond(self.cfg, self.ref, self.messages, on_event=on_event, stream=True)
        except Exception as exc:
            self.call_from_thread(self._fail, exc)
            return
        self.call_from_thread(self._show_reply, reply)

    def _add_process_event(self, process, event):
        process.add_event(self.ui_theme, event)
        if event.get("type") == "ask_user":
            self._release_pending_ask(RuntimeError("ask_user superseded by a newer question"))
            self._pending_ask = event
            self._log("ask_user", event)
        self.log_widget.scroll_end(animate=False)

    def _show_reply(self, reply):
        self._set_spinner(False)
        usage = getattr(reply, "usage", None) or {}
        self._turn_usage = usage
        total = usage.get("total_tokens")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            self._session_tokens += int(total)
        self._update_usage()
        self._log("reply", reply.text)
        self._finish_turn()

    def _fail(self, exc):
        self._set_spinner(False)
        self._release_pending_ask(exc)
        rollback_turn(self.messages)
        self._log("error", exc)
        self._finish_turn()
