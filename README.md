# chaos-harness

Team Chaos's homemade CLI agent harness. A learning project: a hand-rolled LLM
agent loop (no framework) with a tool registry, JSONL tracing, and a CLI.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
export ANTHROPIC_API_KEY=...

chaos "list the files here and summarize them"   # one-shot
chaos                                            # interactive session (/exit to quit)
```

The model defaults to `claude-sonnet-4-5`; override with `--model` or the
`CHAOS_MODEL` env var.

## Layout

- `chaos/cli.py` — argument parsing, one-shot mode and interactive REPL
- `chaos/agent.py` — the agent loop: model call → tool calls → repeat
- `chaos/tools.py` — tool registry + built-in tools
- `chaos/tracing.py` — JSONL trace logging to `.chaos/traces.jsonl` (disable with `--no-trace`)

## Adding a tool

```python
from chaos.tools import tool

@tool
def word_count(text: str) -> str:
    """Count the words in the given text."""
    return str(len(text.split()))
```

Type hints become the JSON schema the model sees; the docstring becomes the
tool description.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use a fake model client, so no API key is needed.
