import json
import os
from pathlib import Path

from . import config as config_mod
from . import tools as tools_mod
from .llm import Reply, chat

SYSTEM_PROMPT = (
    "You are CHAOS, a hackathon agent. The user's project is the workspace rooted at {root}. "
    "You can read and edit its files with the provided tools; all tool paths are relative to that root. "
    "Prefer edit_file's exact search/replace over rewriting whole files, and re-read a file after a failed edit. "
    "Keep replies short — the demo is on stage."
)


def _context(cfg):
    root = Path(cfg.get("workspace_root") or os.getcwd())
    return tools_mod.ToolContext(
        root=root,
        max_file_bytes=int(cfg.get("max_file_bytes", tools_mod.DEFAULT_MAX_FILE_BYTES)),
        max_result_bytes=int(cfg.get("max_result_bytes", tools_mod.DEFAULT_MAX_RESULT_BYTES)),
    )


def _parsed_arguments(raw):
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    return parsed if isinstance(parsed, dict) else raw


def respond(cfg, ref, messages):
    """One agent turn: run the tool loop until the model answers without tool calls."""
    base_url, api_key, model = config_mod.resolve(cfg, ref)
    ctx = _context(cfg)
    max_rounds = int(cfg.get("max_tool_rounds", tools_mod.DEFAULT_MAX_TOOL_ROUNDS))
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT.format(root=ctx.root.resolve())})
    events = []
    for _ in range(max_rounds):
        reply = chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools_mod.schemas(),
        )
        if not reply.tool_calls:
            messages.append({"role": "assistant", "content": reply.text})
            return reply._replace(events=tuple(events))
        messages.append(
            {
                "role": "assistant",
                "content": reply.text,
                "tool_calls": [dict(call) for call in reply.tool_calls],
            }
        )
        for call in reply.tool_calls:
            result = tools_mod.execute(call["name"], call["arguments"], ctx)
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": "unparseable tool result"}
            events.append(
                {
                    "tool": call["name"],
                    "arguments": _parsed_arguments(call["arguments"]),
                    "result": parsed,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": result,
                }
            )
    limit_text = f"stopped after {max_rounds} tool rounds — ask me to continue"
    messages.append({"role": "assistant", "content": limit_text})
    return Reply(text=limit_text, events=tuple(events))
