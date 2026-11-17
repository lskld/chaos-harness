from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from . import config as config_mod

MASCOT = """\
  ▀ ▄ ▀
 ▄█▀█▀█▄
 █▀   ▀█
 █ {face} █
 ▀█████▀"""

MASCOT_FLAME_LINES = 2
MASCOT_IDLE_FACE = ">_<"
THINK_FACES = ["-_-", "o_O", "x_x", ">_<"]

NAME = "CHAOS"
TAGLINE = "hackathon agent harness · made by Team Chaos"
HELP_HINT = "type /help for the list of commands"


def mascot_text(face=MASCOT_IDLE_FACE, up=False, theme=None):
    theme = theme or config_mod.DEFAULT_THEME
    lines = MASCOT.format(face=face).splitlines()
    width = max(len(line) for line in lines)
    text = Text()
    if up:
        text.append("\n")
    for i, line in enumerate(lines):
        style = theme["banner"] if i < MASCOT_FLAME_LINES else theme["mascot"]
        text.append(line.center(width) + "\n", style=style)
    if not up:
        text.append("\n")
    return text


def render_banner(theme, ref):
    name = Text(NAME, style=theme["banner"])
    tagline = Text(TAGLINE, style=theme["info"])
    model = Text(f"model: {ref}", style=theme["info"])
    hints = Text(HELP_HINT, style=theme["info"])
    return Panel(
        Group(mascot_text(theme=theme), name, tagline, Text(), model, hints),
        border_style=theme["banner"],
        padding=(1, 3),
    )


def render_user(theme, text):
    return Text.from_markup(f"[{theme['prompt']}]❯[/] [{theme['user']}]{escape(text)}[/]")


def render_thinking(theme, reasoning):
    if not reasoning:
        return None
    return Group(
        Text.from_markup(f"[{theme['thinking']}]thinking[/]"),
        Text(reasoning, style=theme["thinking"]),
    )


def render_reply(theme, text):
    return Group(
        Text.from_markup(f"[{theme['assistant']}]chaos[/]"),
        Markdown(text),
    )


def render_info(theme, text):
    return Text.from_markup(f"[{theme['info']}]{escape(text)}[/]")


def render_error(theme, exc):
    return Text.from_markup(f"[{theme['error']}]error: {escape(str(exc))}[/]")


def print_banner(console, theme, ref):
    console.print(render_banner(theme, ref))


def print_thinking(console, theme, reasoning):
    block = render_thinking(theme, reasoning)
    if block is not None:
        console.print(block)


def print_reply(console, theme, text):
    console.print(render_reply(theme, text))


def print_info(console, theme, text):
    console.print(render_info(theme, text))


def print_error(console, theme, exc):
    console.print(render_error(theme, exc))


def prompt_input(console, theme):
    return Prompt.ask(f"[{theme['prompt']}]❯[/]", console=console)
