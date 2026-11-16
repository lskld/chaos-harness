from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

MASCOT = """\
   ▄██▄
  █▀██▀█
 █ {face} █
 █  ▀▀  █
  ▀████▀"""

MASCOT_IDLE_FACE = ">_<"
THINK_FACES = ["-_-", "o_O", "x_x", ">_<"]


def mascot_text(face=MASCOT_IDLE_FACE, up=False):
    lines = MASCOT.format(face=face).splitlines()
    width = max(len(line) for line in lines)
    art = "\n".join(line.center(width) for line in lines)
    art = "\n" + art if up else art + "\n"
    return Text(art, style="bold red")


def render_banner(theme, ref):
    name = Text("CHAOS", style=theme["banner"])
    tagline = Text("hackathon agent harness · made by Team Chaos", style=theme["info"])
    model = Text(f"model: {ref}", style=theme["info"])
    hints = Text("/model switch model · /clear reset · /exit quit", style=theme["info"])
    return Panel(
        Group(mascot_text(), name, tagline, Text(), model, hints),
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
