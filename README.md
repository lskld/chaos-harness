# chaos-harness

A hackathon-specific, bring-your-own-model agent CLI, made by Team Chaos — free
for anyone to use, fork, and adapt.

## Quickstart

```bash
pip install -e .
chaos          # first run writes an example ~/.chaos/config.json — fill in a provider
chaos "hi"     # one-shot prompt
```

## Config (`~/.chaos/config.json`)

The file is provider-agnostic: any API with an OpenAI-compatible
`POST /chat/completions` endpoint works. Structure:

```json
{
  "default_model": "",
  "providers": {
    "my-provider": {
      "base_url": "",
      "api_key": "",
      "models": []
    }
  },
  "theme_name": "fire"
}
```

Fill in one `providers` block per API you want to use: `base_url` is the API
root, `api_key` its key, `models` the model IDs it serves. Set `default_model`
to `"my-provider/<model-id>"`, or pick a model per run with `--model
provider/model` or the `/model` command inside the CLI. Adding a provider block
makes all of its models available immediately. Pick a color theme with
`"theme_name"` (`fire`, `ocean`, `forest`, `sunset`, `mono` — or `/theme` in the
CLI). To customize individual colors, add an optional `theme` block that
overrides keys of the selected preset — all keys are optional:

```json
"theme": {
  "background": "#1a0d0a",
  "banner": "bold #ffc94d",
  "mascot": "bold #ff5f6d",
  "prompt": "#ff87a2",
  "user": "#fff3e8",
  "assistant": "#ffd76a",
  "error": "bold #ff4040",
  "info": "#c4a3a3",
  "thinking": "italic #c4a3a3"
}
```

Values are Rich styles (`"#ff87a2"`, `"bold #ff4040"`, `"italic #c4a3a3"`).
Keys: `background` (app background), `banner` (title), `mascot`, `prompt`
(input border), `user`, `assistant`, `error`, `info`, `thinking`
(thought-process dropdown).

`chaos` takes over the whole terminal (alternate screen): a top bar with the
current model and an evil fireball mascot top-right — while the model thinks it
bobs up and down, cycles thinking faces, and shows a `thinking…` spinner line below
it. Below that: a scrollable chat and an input line docked at the bottom. Each
answer is preceded by a collapsed `▶ thought process` dropdown — click it to
expand and watch the turn live: the model's reasoning streamed token by token
(when the provider streams it), every tool call as it is made
(`⚒ edit_file … …` while running, then its result with a unified diff);
replies render as markdown below the dropdown. Streaming uses the API's
`stream: true` SSE mode with a fallback to plain completions.
Commands: `/help` (lists them all), `/exit` (or ctrl+q), `/clear`,
`/model [provider/model]`, `/theme`.
`/theme` opens a menu you navigate with ↑/↓ + enter (esc closes). Built-in themes:
`fire` (default), `ocean`, `forest`, `sunset`, `mono` — switching re-themes the
whole app live and **saves the choice** to `~/.chaos/config.json` (`theme_name`),
so the app reopens with your theme; `/theme ocean` also works directly. When
stdin is piped it falls back to a plain print loop; `chaos "prompt"` stays
one-shot and pipe-friendly (one-shot prints only the final reply, no tool output).

## Tools (file editing)

The agent can read and edit your code through function tools, shown live in the
turn's `thought process` dropdown as `⚒ <tool> <path>` lines with a unified diff
for every change:

- `read_file(path, offset?, limit?)` — read a UTF-8 text file (optional line window)
- `list_files(path?, pattern?)` — list files under a directory, glob-filtered
- `edit_file(path, old_str, new_str)` — exact search/replace; `old_str` must match
  exactly once, otherwise the edit is refused and the model re-reads the file
- `write_file(path, content, overwrite?)` — create a file; overwriting an existing
  file requires `overwrite: true`

Safety: all tool paths are resolved against the **workspace root** (the directory
you launched `chaos` from, or `workspace_root` in the config) and anything outside
it — including symlink escapes and absolute paths — is refused. Binary files and
oversized files/results are capped. Optional config keys (all have defaults):
`"workspace_root"`, `"max_file_bytes"` (200000), `"max_result_bytes"` (20000),
`"max_tool_rounds"` (10, the tool-loop iteration cap per turn).

## Automatic PR review

Every pull request gets an automated review comment from a Mistral model
(default `mistral-large-latest`, the current Mistral Large 4). The
`PR review` workflow (`.github/workflows/pr-review.yml`) fetches the PR diff
via the GitHub API, sends it together with `AGENTS.md` to
`https://api.mistral.ai/v1/chat/completions` (script:
`.github/scripts/pr_review.py`, which reuses `chaos.llm.chat`), and posts the
review as a PR comment: a verdict (approve / changes requested / comment), a
summary, and findings with `file:line` references. It runs on `opened`,
`synchronize` and `reopened`.

Setup (repo admin, once):

1. Add a `MISTRAL_API_KEY` secret (Settings → Secrets and variables → Actions).
2. Optionally set repo variables `REVIEW_MODEL` (any Mistral model id, e.g. a
   pinned dated id) and `MISTRAL_BASE_URL` (defaults to `https://api.mistral.ai/v1`).

The review is advisory: it comments on the PR but does not block merging —
you (or an agent) verify the findings and fix what needs fixing before merge.
PRs from forks skip the review automatically (secrets are not exposed to
them), so the check stays green for them.

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

Layout and conventions for contributors (human or AI) are in `AGENTS.md`.
