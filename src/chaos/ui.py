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


def print_banner(console, theme, ref):
    fire = Text(FIREBALL, style="bold red")
    name = Text("CHAOS", style=theme["banner"])
    tagline = Text("hackathon agent harness · made by Team Chaos", style=theme["info"])
    model = Text(f"model: {ref}", style=theme["info"])
    hints = Text("/model switch model · /clear reset · /exit quit", style=theme["info"])
    console.print(
        Panel(
            Group(fire, name, tagline, Text(), model, hints),
            border_style=theme["banner"],
            padding=(1, 3),
        )
    )


def print_thinking(console, theme, reasoning):
    if reasoning:
        console.print(
            Panel(
                escape(reasoning),
                title=f"[{theme['thinking']}]thinking[/]",
                title_align="left",
                border_style=theme["thinking"],
            )
        )


def print_reply(console, theme, text):
    console.print(
        Panel(
            Markdown(text),
            title=f"[{theme['assistant']}]chaos[/]",
            title_align="left",
            border_style=theme["assistant"],
        )
    )


def print_info(console, theme, text):
    console.print(f"[{theme['info']}]{escape(text)}[/]")


def print_error(console, theme, exc):
    console.print(f"[{theme['error']}]error: {escape(str(exc))}[/]")


def prompt_input(console, theme):
    return Prompt.ask(f"[{theme['prompt']}]❯[/]", console=console)
