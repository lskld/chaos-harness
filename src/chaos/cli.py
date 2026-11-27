import argparse
import sys

from rich.console import Console
from rich.markup import escape

from . import commands
from . import config as config_mod
from . import tools as tools_mod
from . import ui
from .agent import respond, rollback_turn
from .session import Session


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="chaos",
        description="chaos — hackathon agent CLI with bring-your-own-model config",
    )
    parser.add_argument("prompt", nargs="?", help="one-shot prompt; omit to open the interactive CLI")
    parser.add_argument("--model", help="provider/model to use (default: default_model from config)")
    parser.add_argument(
        "--config",
        default=str(config_mod.DEFAULT_CONFIG_PATH),
        help="config file path (default: %(default)s)",
    )
    return parser.parse_args(argv)


def _print_out(console, theme, out):
    for kind, text in out:
        if kind == "error":
            ui.print_error(console, theme, text)
        else:
            ui.print_info(console, theme, text)


def _ask_event_handler(console, theme):
    """on_event for non-TUI runs: an ask_user event prints the question (and choices)
    and reads the answer line from stdin, resolving the event's future."""
    def on_event(event):
        if event.get("type") != "ask_user":
            return
        ui.print_info(console, theme, f"chaos asks: {event.get('question', '')}")
        choices = event.get("choices") or []
        for index, choice in enumerate(choices, 1):
            ui.print_info(console, theme, f"  {index}) {choice}")
        if choices:
            ui.print_info(console, theme, "  answer with a number or free text:")
        future = event.get("future")
        line = sys.stdin.readline()
        if future is not None:
            future.set_result(line.rstrip("\n") if line else "")
    return on_event


def repl(console, theme, cfg, ref, config_path=None):
    ui.print_banner(console, theme, ref)
    session = Session(cfg, ref, config_path)
    while True:
        try:
            line = ui.prompt_input(console, theme)
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        command = line.strip()
        if not command:
            continue
        name, arg = commands.split(command)
        if name is not None and name not in commands.COMMANDS and " " not in command:
            _, matches = commands.suggestions(command, session.cfg)
            for value, desc in matches:
                ui.print_info(console, theme, f"{value} — {desc}" if desc else value)
            if matches:
                continue
        if name in commands.COMMANDS:
            action, out = session.handle_command(name, arg)
            if action == "exit":
                return
            if action == "pick_model":
                out = session.list_models()
            elif action == "pick_theme":
                out = session.list_themes()
            _print_out(console, theme, out)
            theme = session.theme
            continue
        session.messages.append({"role": "user", "content": command})
        try:
            with console.status(f"[{theme['info']}]thinking…[/]", spinner="dots"):
                reply = respond(
                    session.cfg, session.ref, session.messages,
                    on_event=_ask_event_handler(console, theme),
                )
        except KeyboardInterrupt:
            rollback_turn(session.messages)
            console.print()
            continue
        except Exception as exc:
            rollback_turn(session.messages)
            ui.print_error(console, theme, exc)
            continue
        for event in reply.events:
            ui.print_tool(console, theme, event)
        ui.print_thinking(console, theme, reply.reasoning)
        ui.print_reply(console, theme, reply.text)


def main(argv=None):
    args = parse_args(argv)
    console = Console()
    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as exc:
        console.print(f"[bold red]error: {escape(str(exc))}[/]")
        return 2
    theme = config_mod.theme(cfg)
    warning = tools_mod.root_warning(tools_mod.workspace_root(cfg), args.config)
    if warning:
        console.print(f"[bold yellow]warning: {escape(warning)}[/]")
    ref = args.model or cfg.get("default_model")
    try:
        config_mod.resolve(cfg, ref)
    except config_mod.ConfigError as exc:
        ui.print_error(console, theme, exc)
        return 2
    if args.prompt:
        messages = [{"role": "user", "content": args.prompt}]
        try:
            reply = respond(cfg, ref, messages, on_event=_ask_event_handler(console, theme))
        except KeyboardInterrupt:
            console.print()
            return 130
        except Exception as exc:
            ui.print_error(console, theme, exc)
            return 1
        console.print(reply.text, markup=False)
        return 0
    if sys.stdin.isatty():
        from .app import ChaosApp

        ChaosApp(cfg, ref, args.config).run()
        return 0
    repl(console, theme, cfg, ref, args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
