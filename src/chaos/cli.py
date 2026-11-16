import argparse

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from . import config as config_mod
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


def print_error(console, theme, exc):
    console.print(f"[{theme['error']}]error: {escape(str(exc))}[/]")


def handle_model_command(console, theme, cfg, arg, current):
    if not arg:
        for m in config_mod.list_models(cfg):
            marker = "*" if m == current else " "
            console.print(f"[{theme['info']}]{marker} {m}[/]")
        return current
    try:
        config_mod.resolve(cfg, arg)
    except config_mod.ConfigError as exc:
        print_error(console, theme, exc)
        return current
    console.print(f"[{theme['info']}]switched to {arg}[/]")
    return arg


def repl(console, theme, cfg, ref):
    messages = []
    while True:
        try:
            line = Prompt.ask(f"[{theme['prompt']}]chaos>[/]", console=console)
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        command = line.strip()
        if not command:
            continue
        if command in ("/exit", "/quit"):
            return
        if command == "/clear":
            messages.clear()
            continue
        if command == "/model" or command.startswith("/model "):
            arg = command.split(maxsplit=1)[1] if " " in command else ""
            ref = handle_model_command(console, theme, cfg, arg, ref)
            continue
        messages.append({"role": "user", "content": command})
        try:
            reply = respond(cfg, ref, messages)
        except KeyboardInterrupt:
            console.print()
            return
        except Exception as exc:
            messages.pop()
            print_error(console, theme, exc)
            continue
        console.print(f"[{theme['assistant']}]{escape(reply)}[/]")


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
        print_error(console, theme, exc)
        return 2
    if args.prompt:
        messages = [{"role": "user", "content": args.prompt}]
        try:
            reply = respond(cfg, ref, messages)
        except KeyboardInterrupt:
            console.print()
            return 130
        except Exception as exc:
            print_error(console, theme, exc)
            return 1
        console.print(f"[{theme['assistant']}]{escape(reply)}[/]")
        return 0
    repl(console, theme, cfg, ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
