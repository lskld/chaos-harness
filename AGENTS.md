# AGENTS.md — working on chaos-harness

chaos-harness is a hackathon-specific, bring-your-own-model agent CLI (made by
Team Chaos, open for anyone to use). The agent can read and edit files in the
workspace via function tools.

## Layout (src layout)

- `src/chaos/cli.py` — entry point and composition root: arg parsing, one-shot mode,
  dispatch to the full-screen app on a TTY (plain print loop when piped). No HTTP or
  rendering here.
- `src/chaos/commands.py` — the shared slash commands: one `HELP_LINES` list plus
  `split`/`model_command`/`theme_command` helpers, used by both the app and the piped
  loop so the two can't drift apart.
- `src/chaos/app.py` — the full-screen Textual app: top bar with the current model
  and the animated fireball mascot (top-right, bobs + changes faces while thinking,
  spinner line below it), scrollable log (`VerticalScroll` of `Static`s plus one
  collapsed `ThoughtProcess` collapsible per turn that streams events live),
  input docked at the bottom; the agent call runs in a worker thread and posts
  events back with `call_from_thread`.
- `src/chaos/ui.py` — shared renderables: mascot art/frames, banner, user line,
  thinking/reply blocks, tool events (`render_tool` / `render_tool_call` /
  `render_event` dispatcher for the thought-process dropdown), info/error; used by
  both the app and the piped fallback loop, plus the themed prompt.
- `src/chaos/themes.py` — the built-in color themes (`THEMES`, `DEFAULT_THEME_NAME="fire"`).
- `src/chaos/config.py` — everything about `~/.chaos/config.json`: loading, example
  generation, theme selection/overrides, `provider/model` resolution.
- `src/chaos/llm.py` — all HTTP: a single OpenAI-compatible `POST /chat/completions` call
  (`chat`), plus `chat_stream`, the same call with `stream: true` that parses SSE chunks,
  reports them via `on_delta(field, text)` and accumulates a `Reply` (falls back to plain
  parsing when the API does not return `text/event-stream`).
- `src/chaos/agent.py` — the agent seam: `respond()` runs the tool loop (call model →
  execute tool calls → feed results back) until the model answers without tool calls.
  Pass `on_event` to get typed events (`round` / `tool_call` / `tool_result` / `reply`,
  plus `delta` chunks when `stream=True`) as each step happens; without it, behavior is
  unchanged (events land in `Reply.events`, non-streaming `chat` is used).
- `src/chaos/tools/` — the tool registry: `__init__.py` owns the `Tool` record,
  `schemas()`, `execute()`, and path confinement (`resolve_path`); `filetools.py`
  holds the file tools (`read_file`, `list_files`, `edit_file`, `write_file`).
  New tool families (e.g. shell) add a module here plus one import in `__init__.py`.
- `tests/` — unittest suite; HTTP is mocked, no API key needed.
- `.github/workflows/` + `.github/scripts/pr_review.py` — CI and the automated PR review (Mistral API, posts a review comment per PR); its tests live in `tests/test_pr_review.py`.

## Commands

- install: `pip install -e .`
- run: `chaos` (interactive) or `chaos "prompt"` (one-shot); flags: `--model provider/model`, `--config PATH`
- test: `python -m unittest discover -s tests -v`

## Conventions

- Config lives at `~/.chaos/config.json` (override with `--config`); never commit API keys.
- All providers are called via the OpenAI-compatible chat-completions format.
- Keep modules small and single-purpose; add a feature in the module that owns that concern.
