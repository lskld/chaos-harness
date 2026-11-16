import argparse
import sys

from rich.console import Console
from rich.markup import escape

from . import config as config_mod
from . import ui
from .agent import respond


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


def handle_model_command(console, theme, cfg, arg, current):
    if not arg:
        for m in config_mod.list_models(cfg):
            marker = "*" if m == current else " "
            ui.print_info(console, theme, f"{marker} {m}")
        return current
    try:
        config_mod.resolve(cfg, arg)
    except config_mod.ConfigError as exc:
        ui.print_error(console, theme, exc)
        return current
    ui.print_info(console, theme, f"switched to {arg}")
    return arg


def repl(console, theme, cfg, ref):
    ui.print_banner(console, theme, ref)
    messages = []
    while True:
        try:
            line = ui.prompt_input(console, theme)
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        command = line.strip()
        if not command:
            continue
        if command in ("/exit", "/quit"):
            return
        if command == "/help":
            for line in (
                "/help — show this list",
                "/model [provider/model] — list or switch model",
                "/theme [name] — pick a color theme",
                "/clear — clear the chat",
                "/exit — quit",
            ):
                ui.print_info(console, theme, line)
            continue
        if command == "/clear":
            messages.clear()
            ui.print_info(console, theme, "history cleared")
            continue
        if command == "/model" or command.startswith("/model "):
            arg = command.split(maxsplit=1)[1] if " " in command else ""
            ref = handle_model_command(console, theme, cfg, arg, ref)
            continue
        messages.append({"role": "user", "content": command})
        try:
            with console.status(f"[{theme['info']}]thinking…[/]", spinner="dots"):
                reply = respond(cfg, ref, messages)
        except KeyboardInterrupt:
            messages.pop()
            console.print()
            return
        except Exception as exc:
            messages.pop()
            ui.print_error(console, theme, exc)
            continue
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
    ref = args.model or cfg.get("default_model")
    try:
        config_mod.resolve(cfg, ref)
    except config_mod.ConfigError as exc:
        ui.print_error(console, theme, exc)
        return 2
    if args.prompt:
        messages = [{"role": "user", "content": args.prompt}]
        try:
            reply = respond(cfg, ref, messages)
        except KeyboardInterrupt:
            console.print()
            return 130
        except Exception as exc:
            ui.print_error(console, theme, exc)
            return 1
        console.print(reply.text)
        return 0
    if sys.stdin.isatty():
        from .app import ChaosApp

        ChaosApp(cfg, ref).run()
        return 0
    repl(console, theme, cfg, ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
