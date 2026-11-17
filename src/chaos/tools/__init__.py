import json
from pathlib import Path
from typing import Callable, NamedTuple

DEFAULT_MAX_FILE_BYTES = 200_000
DEFAULT_MAX_RESULT_BYTES = 20_000
DEFAULT_MAX_TOOL_ROUNDS = 10


class ToolError(Exception):
    pass


class ToolContext(NamedTuple):
    root: Path
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES


class Tool(NamedTuple):
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], dict]


def resolve_path(ctx, raw):
    """Resolve a tool-supplied path against the workspace root; refuse escapes."""
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("path must be a non-empty string")
    root = ctx.root.resolve()
    candidate = (root / raw).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ToolError(f"path {raw!r} is outside the workspace root ({root})")
    return candidate


def display_path(ctx, path):
    try:
        return str(path.relative_to(ctx.root.resolve()))
    except ValueError:
        return str(path)


def schemas():
    """OpenAI-compatible tool schemas for the chat-completions payload."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in ALL_TOOLS
    ]


def execute(name, arguments, ctx):
    """Run one tool call; always returns a JSON string (ok or error) for the tool message."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return json.dumps({"ok": False, "error": f"unknown tool {name!r}"})
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "error": f"invalid JSON arguments for {name}: {exc}"})
    else:
        args = arguments
    if not isinstance(args, dict):
        return json.dumps({"ok": False, "error": f"arguments for {name} must be a JSON object"})
    try:
        result = tool.handler(args, ctx)
    except ToolError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    text = json.dumps(result)
    if len(text) > ctx.max_result_bytes:
        overflow = len(text) - ctx.max_result_bytes
        text = text[: ctx.max_result_bytes] + f'... [truncated, {overflow} more bytes]'
    return text


from . import filetools  # noqa: E402

ALL_TOOLS = tuple(filetools.TOOLS)
_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}
