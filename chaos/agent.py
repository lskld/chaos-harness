import json

from .tools import TOOLS, schemas

DEFAULT_SYSTEM_PROMPT = (
    "You are Chaos, the CLI agent built by Team Chaos. "
    "Reason step by step, use the tools available to you, and keep answers concise."
)


class MaxTurnsExceeded(Exception):
    pass


def run(client, messages, *, model, registry=TOOLS, system=DEFAULT_SYSTEM_PROMPT,
        max_turns=10, tracer=None):
    """Run the agent loop against a messages list, mutating it in place.

    Returns the final assistant text. Raises MaxTurnsExceeded if the model
    keeps requesting tools past max_turns.
    """
    for _ in range(max_turns):
        if tracer:
            tracer.log("request", model=model, messages=messages)
        response = client.messages.create(
            model=model,
            system=system,
            messages=messages,
            tools=schemas(registry),
            max_tokens=4096,
        )
        if tracer:
            tracer.log("response", stop_reason=response.stop_reason,
                       content=[_block_summary(b) for b in response.content])
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            return _text_of(response)

        results = [_execute_tool(registry, block, tracer) for block in tool_uses]
        messages.append({"role": "user", "content": results})
    raise MaxTurnsExceeded(f"agent did not finish within {max_turns} turns")


def _execute_tool(registry, block, tracer):
    func = registry.get(block.name)
    if func is None:
        content, is_error = f"unknown tool: {block.name}", True
    else:
        try:
            result = func(**block.input)
            content = result if isinstance(result, str) else json.dumps(result, default=str)
            is_error = False
        except Exception as exc:
            content, is_error = f"{type(exc).__name__}: {exc}", True
    if tracer:
        tracer.log("tool_result", tool=block.name, is_error=is_error, result=content)
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": content,
        "is_error": is_error,
    }


def _text_of(response):
    return "".join(b.text for b in response.content if b.type == "text")


def _block_summary(block):
    summary = {"type": block.type}
    for attr in ("text", "name"):
        if getattr(block, attr, None) is not None:
            summary[attr] = getattr(block, attr)
    return summary
