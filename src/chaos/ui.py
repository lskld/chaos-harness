from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

FIREBALL = r"""
     ,  )  (  ,
    (  (  )  )
     )  )(  (
    (  /  \  )
     \ \  / /
      )  ( (
     (______)
"""


def render_banner(theme, ref):
    fire = Text(FIREBALL, style="bold red")
    name = Text("CHAOS", style=theme["banner"])
    tagline = Text("hackathon agent harness · made by Team Chaos", style=theme["info"])
    model = Text(f"model: {ref}", style=theme["info"])
    hints = Text("/model switch model · /clear reset · /exit quit", style=theme["info"])
    return Panel(
        Group(fire, name, tagline, Text(), model, hints),
        border_style=theme["banner"],
        padding=(1, 3),
    )


def render_user(theme, text):
    return Text.from_markup(f"[{theme['prompt']}]❯[/] [{theme['user']}]{escape(text)}[/]")


def render_thinking(theme, reasoning):
    if not reasoning:
        return None
    return Panel(
        escape(reasoning),
        title=f"[{theme['thinking']}]thinking[/]",
        title_align="left",
        border_style=theme["thinking"],
    )


def render_reply(theme, text):
    return Panel(
        Markdown(text),
        title=f"[{theme['assistant']}]chaos[/]",
        title_align="left",
        border_style=theme["assistant"],
    )


def render_info(theme, text):
    return Text.from_markup(f"[{theme['info']}]{escape(text)}[/]")


def render_error(theme, exc):
    return Text.from_markup(f"[{theme['error']}]error: {escape(str(exc))}[/]")


def print_banner(console, theme, ref):
    console.print(render_banner(theme, ref))


def print_thinking(console, theme, reasoning):
    panel = render_thinking(theme, reasoning)
    if panel is not None:
        console.print(panel)


def print_reply(console, theme, text):
    console.print(render_reply(theme, text))


def print_info(console, theme, text):
    console.print(render_info(theme, text))


def print_error(console, theme, exc):
    console.print(render_error(theme, exc))


def prompt_input(console, theme):
    return Prompt.ask(f"[{theme['prompt']}]❯[/]", console=console)
