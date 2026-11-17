import json
import os
from pathlib import Path

from . import config as config_mod
from . import tools as tools_mod
from .llm import Reply, chat, chat_stream

SYSTEM_PROMPT = (
    "You are CHAOS, a hackathon agent. The user's project is the workspace rooted at {root}. "
    "Use the tools only when the task requires reading or editing files, or when the user explicitly asks — "
    "never list or read the workspace just to get oriented; for greetings, questions and small talk, "
    "answer directly without any tool call. "
    "When you do use tools, all tool paths are relative to that root. "
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


def respond(cfg, ref, messages, on_event=None, stream=False):
    """One agent turn: run the tool loop until the model answers without tool calls.

    If on_event is given, it is called with a typed event as each step happens:
    {"type": "round", "reasoning"?, "content"?}, {"type": "tool_call", ...},
    {"type": "tool_result", ...} and {"type": "reply", "text": ...}; with stream=True
    it also gets {"type": "delta", "field": "content"|"reasoning", "text": ...} per chunk.
    A round's "content" carries any text the model produced before calling tools.
    """
    base_url, api_key, model = config_mod.resolve(cfg, ref)
    ctx = _context(cfg)
    max_rounds = int(cfg.get("max_tool_rounds", tools_mod.DEFAULT_MAX_TOOL_ROUNDS))
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT.format(root=ctx.root.resolve())})
    events = []

    def emit(event):
        if on_event is not None:
            on_event(event)

    for _ in range(max_rounds):
        streamed_fields = []
        if stream:
            def on_delta(field, text):
                streamed_fields.append(field)
                emit({"type": "delta", "field": field, "text": text})

            reply = chat_stream(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                tools=tools_mod.schemas(),
                on_delta=on_delta,
            )
        else:
            reply = chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                tools=tools_mod.schemas(),
            )
        round_event = {"type": "round"}
        if reply.reasoning and "reasoning" not in streamed_fields:
            round_event["reasoning"] = reply.reasoning
        if reply.tool_calls and reply.text and "content" not in streamed_fields:
            round_event["content"] = reply.text
        if len(round_event) > 1:
            emit(round_event)
        if not reply.tool_calls:
            messages.append({"role": "assistant", "content": reply.text})
            emit({"type": "reply", "text": reply.text})
            return reply._replace(events=tuple(events))
        messages.append(
            {
                "role": "assistant",
                "content": reply.text,
                "tool_calls": [dict(call) for call in reply.tool_calls],
            }
        )
        for call in reply.tool_calls:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            parsed_arguments = _parsed_arguments(arguments)
            emit({"type": "tool_call", "tool": name, "arguments": parsed_arguments})
            result = tools_mod.execute(name, arguments, ctx)
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": "unparseable tool result"}
            event = {
                "type": "tool_result",
                "tool": name,
                "arguments": parsed_arguments,
                "result": parsed,
            }
            events.append(event)
            emit(event)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,
                    "content": result,
                }
            )
    limit_text = f"stopped after {max_rounds} tool rounds — ask me to continue"
    messages.append({"role": "assistant", "content": limit_text})
    emit({"type": "reply", "text": limit_text})
    return Reply(text=limit_text, events=tuple(events))
