# AGENTS.md — working on chaos-harness

chaos-harness is a hackathon-specific, bring-your-own-model agent CLI. Python 3.12+, src layout, unittest suite.

## Layout

- `src/chaos/cli.py` — entry point and composition root: arg parsing, one-shot mode, dispatch to the full-screen app on a TTY vs the piped loop.
- `src/chaos/app.py` — the full-screen Textual app; the agent call runs in a worker thread.
- `src/chaos/ui.py`, `src/chaos/commands.py`, `src/chaos/themes.py` — shared renderables, slash commands, color themes.
- `src/chaos/agent.py` — the agent tool loop (`respond()`); `src/chaos/llm.py` — all HTTP (OpenAI-compatible chat completions, plain + SSE streaming).
- `src/chaos/config.py` — `~/.chaos/config.json` loading and provider/model resolution.
- `src/chaos/tools/` — the agent's tools: registry in `__init__.py` (`Tool`, `schemas()`, `execute()`, path confinement) plus one module per tool; a new tool adds one module here plus one import in `__init__.py`.
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
- Keep `README.md` and `AGENTS.md` minimal: update them only when the change is something a
  reader must actually know, not merely because something new was added.
  - `README.md`: only for user-facing usage — new or changed slash commands (also add them
    to the in-app `/help` list), CLI flags, config keys, or workflows the user interacts
    with. A new tool, module, or internal behavior does not qualify.
  - `AGENTS.md`: only when the architecture or these conventions change. Describe areas by
    what they are, never enumerate the individual tools or files inside a directory —
    `src/chaos/tools/` stays a one-line overview no matter how many tools it gains.
  - When in doubt, leave both files untouched.
- Keep changes small and focused; add or update tests in `tests/` for anything you touch.
