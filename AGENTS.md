# AGENTS.md — working on chaos-harness

chaos-harness is a hackathon-specific, bring-your-own-model agent CLI (made by
Team Chaos, open for anyone to use). Current scope: prompt → answer only, no
tool calling yet.

## Layout (src layout)

- `src/chaos/cli.py` — entry point and composition root: arg parsing, interactive
  REPL, slash commands. No HTTP or config-file IO here.
- `src/chaos/config.py` — everything about `~/.chaos/config.json`: loading, example
  generation, theme, `provider/model` resolution.
- `src/chaos/llm.py` — all HTTP: a single OpenAI-compatible `POST /chat/completions` call.
- `src/chaos/agent.py` — the agent seam: v1 makes one call per turn; tool calling,
  budget tracking, and tracing plug in here later.
- `tests/` — unittest suite; HTTP is mocked, no API key needed.

## Commands

- install: `pip install -e .`
- run: `chaos` (interactive) or `chaos "prompt"` (one-shot); flags: `--model provider/model`, `--config PATH`
- test: `python -m unittest discover -s tests -v`

## Conventions

- Config lives at `~/.chaos/config.json` (override with `--config`); never commit API keys.
- All providers are called via the OpenAI-compatible chat-completions format.
- Keep modules small and single-purpose; add a feature in the module that owns that concern.
