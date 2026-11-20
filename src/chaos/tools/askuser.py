import concurrent.futures
import re

from . import Tool, ToolContext, ToolError

_CHOICE_NUMBER_PREFIX = re.compile(r"^\s*\d{1,2}\s*[.)]\s+")


def _plain_choice(choice):
    """Drop a leading list number ('1. postgres' -> 'postgres') so the UI's own numbering
    doesn't render twice when the model passes pre-numbered choices."""
    stripped = _CHOICE_NUMBER_PREFIX.sub("", choice, count=1).strip()
    return stripped or choice

ASK_USER_PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "the question to show the user",
        },
        "choices": {
            "type": "array",
            "items": {"type": "string"},
            "description": "optional choices the user can pick from; they may also answer freely",
        },
    },
    "required": ["question"],
    "additionalProperties": False,
}


def ask_user(args, ctx: ToolContext):
    """Pause the tool loop until the user answers: emit an ask_user event carrying a
    Future through ctx.emit, block on it, and return the answer as the tool result.
    A numeric answer matching a choice is mapped to that choice."""
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ToolError("question must be a non-empty string")
    choices = args.get("choices")
    if choices is not None:
        if not isinstance(choices, list) or any(
            not isinstance(choice, str) or not choice.strip() for choice in choices
        ):
            raise ToolError("choices must be a list of non-empty strings")
        if not choices:
            choices = None
        else:
            choices = [_plain_choice(choice) for choice in choices]
    if ctx.emit is None:
        raise ToolError("ask_user needs an interactive session, but no event listener is attached")
    future = concurrent.futures.Future()
    ctx.emit({"type": "ask_user", "question": question, "choices": choices, "future": future})
    answer = future.result()
    if answer is None:
        answer = ""
    answer = str(answer).strip()
    # isdecimal, not isdigit: superscripts like '²' are isdigit() but not int()-parseable
    if choices and answer.isdecimal() and 1 <= int(answer) <= len(choices):
        answer = choices[int(answer) - 1]
    return {"ok": True, "answer": answer}


TOOLS = (
    Tool(
        "ask_user",
        "Pause the run and ask the user a question when the task is ambiguous or the decision is "
        "theirs (e.g. 'which database?', 'overwrite this file?'); optionally pass choices they can "
        "pick from. Blocks until the user answers; the answer comes back as this tool's result.",
        ASK_USER_PARAMETERS,
        ask_user,
    ),
)
