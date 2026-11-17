import argparse
import sys

from rich.console import Console
from rich.markup import escape

from . import commands
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


def _print_out(console, theme, out):
    for kind, text in out:
        if kind == "error":
            ui.print_error(console, theme, text)
        else:
            ui.print_info(console, theme, text)


def repl(console, theme, cfg, ref, config_path=None):
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
        name, arg = commands.split(command)
        if name in commands.COMMANDS:
            if name in ("/exit", "/quit"):
                return
            if name == "/help":
                for text in commands.HELP_LINES:
                    ui.print_info(console, theme, text)
                continue
            if name == "/clear":
                messages.clear()
                ui.print_info(console, theme, "history cleared")
                continue
            if name == "/model":
                ref, out = commands.model_command(cfg, arg, ref)
                _print_out(console, theme, out)
                continue
            if name == "/theme":
                new_name, out = commands.theme_command(arg, cfg.get("theme_name"))
                _print_out(console, theme, out)
                if new_name:
                    cfg["theme_name"] = new_name
                    theme = config_mod.theme(cfg, new_name)
                    if config_path is not None:
                        try:
                            config_mod.save(config_path, cfg)
                        except OSError as exc:
                            ui.print_error(console, theme, f"could not save theme to config: {exc}")
                continue
        messages.append({"role": "user", "content": command})
        try:
            with console.status(f"[{theme['info']}]thinking…[/]", spinner="dots"):
                reply = respond(cfg, ref, messages)
        except KeyboardInterrupt:
            messages.pop()
            console.print()
            continue
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

        ChaosApp(cfg, ref, args.config).run()
        return 0
    repl(console, theme, cfg, ref, args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
