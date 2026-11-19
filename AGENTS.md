# AGENTS.md — working on chaos-harness

chaos-harness is a hackathon-specific, bring-your-own-model agent CLI (Team
Chaos, MIT, free to fork and adapt). Python 3.12+, src layout, unittest suite.

This file stays lean on purpose: only what is needed every session. For a deep
dive into an area, use a skill or read that module's source/docstrings.

## Layout

- `src/chaos/cli.py` — entry point and composition root: arg parsing, one-shot mode, dispatch to the full-screen app on a TTY vs the piped loop.
- `src/chaos/app.py` — the full-screen Textual app; the agent call runs in a worker thread.
- `src/chaos/ui.py`, `src/chaos/commands.py`, `src/chaos/themes.py` — shared renderables, slash commands, color themes.
- `src/chaos/agent.py` — the agent tool loop (`respond()`); `src/chaos/llm.py` — all HTTP (OpenAI-compatible chat completions, plain + SSE streaming).
- `src/chaos/config.py` — `~/.chaos/config.json` loading and provider/model resolution.
- `src/chaos/tools/` — tool registry (`__init__.py`: `Tool`, `schemas()`, `execute()`, path confinement) plus the file tools in `filetools.py`; a new tool family adds one module here plus one import in `__init__.py`.
- `tests/` — unittest suite; HTTP is mocked, no API key needed.
- `.github/` — CI workflows and `scripts/pr_review.py`, the automated PR review (its review prompt reads this file as the source of repo conventions).

## Commands

- install: `pip install -e .`
- run: `chaos` (interactive) or `chaos "prompt"` (one-shot); flags: `--model provider/model`, `--config PATH`
- test: `python -m unittest discover -s tests -v`

## Conventions

- Config lives at `~/.chaos/config.json` (override with `--config`); never commit API keys.
- All providers are called via the OpenAI-compatible chat-completions format.
- Keep modules small and single-purpose; add a feature in the module that owns that concern.
- Keep changes small and focused; add or update tests in `tests/` for anything you touch.
