# AGENTS.md — working on chaos-harness

chaos-harness is a hackathon-specific, bring-your-own-model agent CLI (made by
Team Chaos, open for anyone to use). Current scope: prompt → answer only, no
tool calling yet.

## Layout (src layout)

- `src/chaos/cli.py` — entry point and composition root: arg parsing, one-shot mode,
  dispatch to the full-screen app on a TTY (plain print loop when piped). No HTTP or
  rendering here.
- `src/chaos/commands.py` — the shared slash commands: one `HELP_LINES` list plus
  `split`/`model_command`/`theme_command` helpers, used by both the app and the piped
  loop so the two can't drift apart.
- `src/chaos/app.py` — the full-screen Textual app: top bar with the current model
  and the animated fireball mascot (top-right, bobs + changes faces while thinking,
  spinner line below it), scrollable log, input docked at the bottom; the agent call
  runs in a worker thread.
- `src/chaos/ui.py` — shared renderables: mascot art/frames, banner, user line,
  thinking/reply blocks, info/error; used by both the app and the piped fallback
  loop, plus the themed prompt.
- `src/chaos/themes.py` — the built-in color themes (`THEMES`, `DEFAULT_THEME_NAME="fire"`).
- `src/chaos/config.py` — everything about `~/.chaos/config.json`: loading, example
  generation, theme selection/overrides, `provider/model` resolution.
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
