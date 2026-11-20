<h1 align="center">🔥 chaos-harness</h1>

<p align="center">
  <b>A hackathon-specific, bring-your-own-model agent CLI — made by Team Chaos.</b><br>
  Limited time, limited credits, a demo that has to work on stage. Free for anyone to use, fork, and adapt.
</p>

<p align="center">
  <a href="https://github.com/lskld/chaos-harness/actions/workflows/ci.yml">
    <img src="https://github.com/lskld/chaos-harness/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/lskld/chaos-harness/actions/workflows/pr-review.yml">
    <img src="https://github.com/lskld/chaos-harness/actions/workflows/pr-review.yml/badge.svg" alt="PR review">
  </a>
  <a href="https://github.com/lskld/chaos-harness/blob/main/pyproject.toml">
    <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+">
  </a>
  <a href="https://github.com/lskld/chaos-harness/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License: MIT">
  </a>
</p>

## Quickstart

```bash
pip install -e .
chaos          # first run writes an example ~/.chaos/config.json — fill in a provider
chaos "hi"     # one-shot prompt
```

Requires Python 3.12+. No API key is needed to install or run the tests — only
to actually chat with a model.

## Usage

```bash
chaos                  # interactive CLI (full-screen on a TTY, plain loop when piped)
chaos "summarize this repo"          # one-shot prompt
chaos "hi" --model my-provider/gpt-x # pick a model for this run
chaos "hi" --config ./ci-config.json # use a different config file
```

Inside the CLI, slash commands:

| Command | What it does |
| --- | --- |
| `/help` | show the command list |
| `/model [provider/model]` | pick or switch model |
| `/theme [name]` | pick a color theme |
| `/deadline [HH:MM\|off]` | set or clear the hackathon countdown (persisted in config, shown as `⏳ H:MM left` in the top bar) |
| `/clear` | clear the chat |
| `/exit` | quit |

The agent can also pause mid-run to ask you something (the `ask_user` tool, e.g.
"which database?" with choices). In the full-screen UI the question appears in the
log — your next input line answers it (type a choice number or free text). In piped
or one-shot mode the question and its choices are printed and the answer is read
from stdin. The answer comes back to the model as the tool result, so it counts
toward `max_tool_rounds` like any other tool call.

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

Never commit API keys — `.chaos/` and `.env` are gitignored, and configured
secrets are redacted from tool output and errors.

## Development

```bash
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -e .
python -m unittest discover -s tests -v              # HTTP is mocked, no API key needed
chaos --help                                         # smoke-check the CLI
```

CI (`.github/workflows/ci.yml`) runs the same tests on Python 3.12, 3.14 and
3.15 plus `chaos --help` on every push and PR.

Layout and conventions for contributors (human or AI) are in
[`AGENTS.md`](AGENTS.md) — read it before opening a PR: src layout, where each
concern lives (CLI, Textual app, agent loop, tools, config, LLM), and the
testing style.

## Automated PR review

Every pull request gets an automated review comment from a Mistral model
(default `mistral-large-latest`, the current Mistral Large 4). The
`PR review` workflow (`.github/workflows/pr-review.yml`) fetches the PR diff
via the GitHub API, sends it together with `AGENTS.md` to
`https://api.mistral.ai/v1/chat/completions` (script:
`.github/scripts/pr_review.py`, which reuses the streaming `chaos.llm.chat_stream`), and posts the
review as a PR comment: a verdict (approve / changes requested / comment), a
summary, and findings with `file:line` references. It runs on `opened`,
`synchronize` and `reopened`, and can be re-run manually from the Actions tab
(`workflow_dispatch`). On fork PRs the `MISTRAL_API_KEY` secret is unavailable,
so the review is skipped gracefully.

## Contributing

Issues and PRs are welcome:

- 🐛 [Report a bug](https://github.com/lskld/chaos-harness/issues/new?template=bug_report.md)
- ✨ [Request a feature](https://github.com/lskld/chaos-harness/issues/new?template=feature_request.md)

Every PR is automatically reviewed (see above) and runs CI on all supported
Python versions. Keep changes small and focused; add or update tests in
`tests/` for anything you touch.

## License

[MIT](LICENSE) — use it, fork it, ship it on stage. 🔥
