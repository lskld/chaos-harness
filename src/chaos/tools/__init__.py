import json
import os
from pathlib import Path
from typing import Callable, NamedTuple

from .. import config as config_mod

DEFAULT_MAX_FILE_BYTES = 200_000
DEFAULT_MAX_RESULT_BYTES = 20_000
DEFAULT_MAX_TOOL_ROUNDS = 10

PROTECTED_DIRS = frozenset({".chaos", ".ssh", ".aws", ".gnupg"})


class ToolError(Exception):
    pass


class ToolContext(NamedTuple):
    root: Path
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES
    secrets: tuple = ()


class Tool(NamedTuple):
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], dict]


def resolve_path(ctx, raw):
    """Resolve a tool-supplied path against the workspace root; refuse escapes
    and paths into protected directories (.chaos, .ssh, ...) regardless of root."""
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("path must be a non-empty string")
    root = ctx.root.resolve()
    candidate = (root / raw).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ToolError(f"path {raw!r} is outside the workspace root ({root})")
    if any(part in PROTECTED_DIRS for part in candidate.relative_to(root).parts):
        raise ToolError(
            f"path {raw!r} is inside a protected directory "
            f"({'/'.join(sorted(PROTECTED_DIRS))}) and is off-limits"
        )
    return candidate


def workspace_root(cfg):
    """The workspace root: the config's workspace_root, or the current directory."""
    return Path(cfg.get("workspace_root") or os.getcwd()).resolve()


def root_warning(root, config_path):
    """Warning text when the root exposes sensitive directories (home, the config
    dir with API keys), else None."""
    root = Path(root).resolve()
    home = Path.home().resolve()
    config_dir = Path(config_path).resolve().parent
    exposed = sorted({str(p) for p in (home, config_dir) if p == root or p.is_relative_to(root)})
    if not exposed:
        return None
    return (
        f"workspace root is {root} — the agent can read and write everything under it, "
        f"including {', '.join(exposed)}. Run chaos from your project directory, "
        f"or set 'workspace_root' in {config_path}."
    )


def _fd_realpath(fd):
    try:
        target = os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return None
    if target.endswith(" (deleted)"):
        target = target[: -len(" (deleted)")]
    return Path(target)


def open_checked(ctx, path, flags, mode=0o666):
    """Open a tool path for I/O, re-checking confinement at open time.

    resolve_path approves the path, but the file is opened later — a symlink
    swapped in between must not escape the root. Re-resolve right before
    opening, open with O_NOFOLLOW, and verify the opened file (via /proc/self/fd
    where available) really lives inside the root.
    """
    root = ctx.root.resolve()
    candidate = Path(path).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ToolError(f"path {display_path(ctx, path)!r} is outside the workspace root ({root})")
    if any(part in PROTECTED_DIRS for part in candidate.relative_to(root).parts):
        raise ToolError(f"path {display_path(ctx, path)!r} is inside a protected directory and is off-limits")
    try:
        fd = os.open(candidate, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except OSError as exc:
        raise ToolError(f"cannot open {display_path(ctx, path)}: {exc.strerror or exc}") from exc
    real = _fd_realpath(fd)
    if real is not None and real != root and not real.is_relative_to(root):
        os.close(fd)
        raise ToolError(f"path {display_path(ctx, path)!r} escaped the workspace root ({root})")
    return fd


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
    """Run one tool call; always returns a JSON string (ok or error) for the tool message.
    Configured secrets are redacted from the result before it leaves the tool layer."""
    def out(payload):
        return config_mod.redact(json.dumps(payload), ctx.secrets)

    tool = _BY_NAME.get(name)
    if tool is None:
        return out({"ok": False, "error": f"unknown tool {name!r}"})
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return out({"ok": False, "error": f"invalid JSON arguments for {name}: {exc}"})
    else:
        args = arguments
    if not isinstance(args, dict):
        return out({"ok": False, "error": f"arguments for {name} must be a JSON object"})
    try:
        result = tool.handler(args, ctx)
    except ToolError as exc:
        return out({"ok": False, "error": str(exc)})
    except Exception as exc:
        return out({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    text = out(result)
    if len(text) > ctx.max_result_bytes:
        overflow = len(text) - ctx.max_result_bytes
        text = text[: ctx.max_result_bytes] + f'... [truncated, {overflow} more bytes]'
    return text


from . import filetools  # noqa: E402

ALL_TOOLS = tuple(filetools.TOOLS)
_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}
