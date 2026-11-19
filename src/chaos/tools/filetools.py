import difflib
import fnmatch
import os
from pathlib import Path

from . import PROTECTED_DIRS, Tool, ToolContext, ToolError, display_path, open_checked, resolve_path

LIST_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
LIST_MAX_ENTRIES = 500

_PATH_PROPERTY = {"type": "string", "description": "path relative to the workspace root"}

READ_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": _PATH_PROPERTY,
        "offset": {
            "type": "integer",
            "description": "1-based line number to start reading from (default: 1)",
            "minimum": 1,
        },
        "limit": {
            "type": "integer",
            "description": "maximum number of lines to return",
            "minimum": 1,
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

LIST_FILES_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {**_PATH_PROPERTY, "description": "directory relative to the workspace root (default: .)"},
        "pattern": {
            "type": "string",
            "description": "glob matched against the relative path, e.g. '*.py' (default: '*')",
        },
    },
    "required": [],
    "additionalProperties": False,
}

EDIT_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": _PATH_PROPERTY,
        "old_str": {
            "type": "string",
            "description": "exact text to replace; must occur exactly once in the file",
        },
        "new_str": {"type": "string", "description": "replacement text"},
    },
    "required": ["path", "old_str", "new_str"],
    "additionalProperties": False,
}

WRITE_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": _PATH_PROPERTY,
        "content": {"type": "string", "description": "full new content of the file"},
        "overwrite": {
            "type": "boolean",
            "description": "must be true to replace an existing file (default: false)",
        },
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}


def _read_text(ctx, path):
    fd = open_checked(ctx, path, os.O_RDONLY)
    try:
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ToolError(f"cannot read {display_path(ctx, path)}: {exc.strerror or exc}") from exc
    if b"\0" in raw[:8192]:
        raise ToolError(f"{display_path(ctx, path)} looks like a binary file; refusing to read it")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{display_path(ctx, path)} is not valid UTF-8 text: {exc}") from exc


def _write_text(ctx, path, text):
    fd = open_checked(ctx, path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        raise ToolError(f"cannot write {display_path(ctx, path)}: {exc.strerror or exc}") from exc


def _read_head(ctx, path, max_bytes):
    """Stream the file in chunks: keep at most the first max_bytes and count the
    total lines, so an over-limit file is never loaded into memory."""
    fd = open_checked(ctx, path, os.O_RDONLY)
    head = bytearray()
    total_lines = 0
    seen = 0
    last = b""
    try:
        with os.fdopen(fd, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                if seen < 8192 and b"\0" in chunk[: 8192 - seen]:
                    raise ToolError(
                        f"{display_path(ctx, path)} looks like a binary file; refusing to read it"
                    )
                seen += len(chunk)
                total_lines += chunk.count(b"\n")
                last = chunk[-1:]
                remaining = max_bytes - len(head)
                if remaining > 0:
                    head.extend(chunk[:remaining])
    except OSError as exc:
        raise ToolError(f"cannot read {display_path(ctx, path)}: {exc.strerror or exc}") from exc
    if last and last != b"\n":
        total_lines += 1
    return bytes(head), total_lines


def _check_size(ctx, path, size):
    if size > ctx.max_file_bytes:
        raise ToolError(
            f"{display_path(ctx, path)} is {size} bytes, over the {ctx.max_file_bytes} byte limit"
        )


def _unified_diff(ctx, path, old, new):
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{display_path(ctx, path)}",
            tofile=f"b/{display_path(ctx, path)}",
        )
    )


def read_file(args, ctx: ToolContext):
    path = resolve_path(ctx, args.get("path"))
    if not path.is_file():
        raise ToolError(f"{display_path(ctx, path)} is not a file")
    offset = args.get("offset", 1)
    limit = args.get("limit")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 1:
        raise ToolError("offset must be a positive integer")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ToolError("limit must be a positive integer")
    over_limit = path.stat().st_size > ctx.max_file_bytes
    raw, total_lines = _read_head(ctx, path, ctx.max_file_bytes)
    if over_limit:
        text = raw.decode("utf-8", errors="ignore")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"{display_path(ctx, path)} is not valid UTF-8 text: {exc}") from exc
        total_lines = len(text.splitlines())
    lines = text.splitlines()
    selected = lines[offset - 1 : offset - 1 + limit if limit is not None else None]
    return {
        "ok": True,
        "path": display_path(ctx, path),
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "truncated": over_limit,
        "content": "\n".join(selected),
    }


def list_files(args, ctx: ToolContext):
    base = resolve_path(ctx, args.get("path") or ".")
    if not base.exists():
        raise ToolError(f"{display_path(ctx, base)} does not exist")
    if not base.is_dir():
        raise ToolError(f"{display_path(ctx, base)} is not a directory")
    pattern = args.get("pattern") or "*"
    if not isinstance(pattern, str):
        raise ToolError("pattern must be a string")
    root = ctx.root.resolve()
    matches = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            d for d in dirnames if d not in LIST_EXCLUDED_DIRS and d not in PROTECTED_DIRS
        )
        for filename in sorted(filenames):
            full = Path(dirpath) / filename
            rel = full.relative_to(root).as_posix()
            if fnmatch.fnmatch(rel, pattern):
                matches.append(rel)
    matches.sort()
    return {
        "ok": True,
        "path": display_path(ctx, base),
        "total": len(matches),
        "truncated": len(matches) > LIST_MAX_ENTRIES,
        "files": matches[:LIST_MAX_ENTRIES],
    }


def edit_file(args, ctx: ToolContext):
    path = resolve_path(ctx, args.get("path"))
    if not path.is_file():
        raise ToolError(f"{display_path(ctx, path)} is not a file")
    old_str = args.get("old_str")
    new_str = args.get("new_str")
    if not isinstance(old_str, str) or old_str == "":
        raise ToolError("old_str must be a non-empty string")
    if not isinstance(new_str, str):
        raise ToolError("new_str must be a string")
    text = _read_text(ctx, path)
    _check_size(ctx, path, len(text.encode("utf-8")))
    count = text.count(old_str)
    if count == 0:
        raise ToolError(
            f"old_str not found in {display_path(ctx, path)} — re-read the file and copy the exact text"
        )
    if count > 1:
        raise ToolError(
            f"old_str matches {count} times in {display_path(ctx, path)} — include more surrounding context"
        )
    new_text = text.replace(old_str, new_str, 1)
    _write_text(ctx, path, new_text)
    return {
        "ok": True,
        "path": display_path(ctx, path),
        "replacements": 1,
        "diff": _unified_diff(ctx, path, text, new_text),
    }


def write_file(args, ctx: ToolContext):
    path = resolve_path(ctx, args.get("path"))
    content = args.get("content")
    if not isinstance(content, str):
        raise ToolError("content must be a string")
    overwrite = args.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise ToolError("overwrite must be a boolean")
    existed = path.exists()
    if existed:
        if not path.is_file():
            raise ToolError(f"{display_path(ctx, path)} exists and is not a regular file")
        if not overwrite:
            raise ToolError(f"{display_path(ctx, path)} already exists — set overwrite=true to replace it")
    size = len(content.encode("utf-8"))
    _check_size(ctx, path, size)
    old = _read_text(ctx, path) if existed else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(ctx, path, content)
    result = {
        "ok": True,
        "path": display_path(ctx, path),
        "bytes": size,
        "created": not existed,
    }
    if existed:
        result["diff"] = _unified_diff(ctx, path, old, content)
    return result


TOOLS = (
    Tool(
        "read_file",
        "Read a UTF-8 text file from the workspace, optionally a window of lines.",
        READ_FILE_PARAMETERS,
        read_file,
    ),
    Tool(
        "list_files",
        "List files under a directory in the workspace, optionally filtered by a glob pattern.",
        LIST_FILES_PARAMETERS,
        list_files,
    ),
    Tool(
        "edit_file",
        "Replace exactly one occurrence of old_str with new_str in an existing file; returns a unified diff.",
        EDIT_FILE_PARAMETERS,
        edit_file,
    ),
    Tool(
        "write_file",
        "Create a new file, or replace an existing one when overwrite=true; returns a unified diff when replacing.",
        WRITE_FILE_PARAMETERS,
        write_file,
    ),
)
