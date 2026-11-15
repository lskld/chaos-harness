import inspect
import os
import typing
from datetime import datetime, timezone

TOOLS = {}

_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


def tool(func):
    TOOLS[func.__name__] = func
    return func


def schemas(registry=TOOLS):
    return [
        {
            "name": func.__name__,
            "description": inspect.getdoc(func) or "",
            "input_schema": _schema_for(func),
        }
        for func in registry.values()
    ]


def _schema_for(func):
    hints = typing.get_type_hints(func)
    sig = inspect.signature(func)
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        py_type = hints.get(name, str)
        properties[name] = {"type": _TYPE_MAP.get(py_type, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


@tool
def current_time() -> str:
    """Return the current date and time in UTC, in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@tool
def echo(text: str) -> str:
    """Repeat back the given text. Useful for testing the tool loop."""
    return text


@tool
def list_files(directory: str = ".") -> str:
    """List the names of files and directories inside a directory, sorted."""
    entries = sorted(os.listdir(directory))
    return "\n".join(entries) if entries else "(empty)"


@tool
def read_file(path: str, max_bytes: int = 20000) -> str:
    """Read a text file and return at most max_bytes of its content."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_bytes)
