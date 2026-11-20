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
        Markdown(text, hyperlinks=False),
    )


def tool_header(event):
    tool = str(event.get("tool", "?"))
    args = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    bits = []
    if "path" in args:
        bits.append(str(args["path"]))
    if tool == "edit_file":
        bits.append(f"replace {len(str(args.get('old_str', '')))} chars")
    elif tool == "write_file":
        bits.append(f"write {len(str(args.get('content', '')))} chars")
    elif tool == "ask_user":
        bits.append(str(args.get("question", "")))
    return " ".join(["⚒", tool, *bits])


def render_tool_call(theme, event):
    return Text.from_markup(f"[{theme['info']}]{escape(tool_header(event))} …[/]")


def render_tool(theme, event):
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    parts = [Text.from_markup(f"[{theme['info']}]{escape(tool_header(event))}[/]")]
    if result and not result.get("ok", True):
        error = escape(str(result.get("error", "")))
        parts.append(Text.from_markup(f"[{theme['error']}]  error: {error}[/]"))
    diff = result.get("diff")
    if diff:
        parts.append(Text(diff, style=theme["info"]))
    answer = result.get("answer")
    if answer is not None:
        parts.append(Text.from_markup(f"[{theme['info']}]  answer: {escape(str(answer))}[/]"))
    return Group(*parts)


def render_ask_user(theme, event):
    question = str(event.get("question", ""))
    parts = [Text.from_markup(f"[{theme['prompt']}]?[/] [{theme['user']}]question: {escape(question)}[/]")]
    choices = event.get("choices") or []
    for index, choice in enumerate(choices, 1):
        parts.append(Text.from_markup(f"[{theme['info']}]  {index}. {escape(str(choice))}[/]"))
    if choices:
        parts.append(Text.from_markup(f"[{theme['info']}]  reply with a number or free text[/]"))
    return Group(*parts)


def render_event(theme, event):
    """Render one streamed agent event for the thought-process dropdown; None to skip."""
    kind = event.get("type")
    if kind == "round":
        parts = []
        reasoning = event.get("reasoning") or ""
        if reasoning:
            rendered = render_thinking(theme, reasoning)
            if rendered is not None:
                parts.append(rendered)
        content = event.get("content") or ""
        if content:
            parts.append(Text(content, style=theme["thinking"]))
        return Group(*parts) if parts else None
    if kind == "tool_call":
        return render_tool_call(theme, event)
    if kind == "tool_result":
        return render_tool(theme, event)
    return None


def render_info(theme, text):
    return Text.from_markup(f"[{theme['info']}]{escape(text)}[/]")


def render_error(theme, exc):
    return Text.from_markup(f"[{theme['error']}]error: {escape(str(exc))}[/]")


def print_banner(console, theme, ref):
    console.print(render_banner(theme, ref))


def print_thinking(console, theme, reasoning):
    if reasoning:
        console.print(render_thinking(theme, reasoning))


def print_reply(console, theme, text):
    console.print(render_reply(theme, text))


def print_tool(console, theme, event):
    console.print(render_tool(theme, event))


def print_info(console, theme, text):
    console.print(render_info(theme, text))


def print_error(console, theme, exc):
    console.print(render_error(theme, exc))


def prompt_input(console, theme):
    return Prompt.ask(f"[{theme['prompt']}]❯[/]", console=console)
