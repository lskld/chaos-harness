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

## Automatic PR review

Every pull request gets an automated review comment from a Mistral model
(default `mistral-large-latest`, the current Mistral Large 4). The
`PR review` workflow (`.github/workflows/pr-review.yml`) fetches the PR diff
via the GitHub API, sends it together with `AGENTS.md` to
`https://api.mistral.ai/v1/chat/completions` (script:
`.github/scripts/pr_review.py`, which reuses the streaming `chaos.llm.chat_stream`), and posts the
review as a PR comment: a verdict (approve / changes requested / comment), a
summary, and findings with `file:line` references. It runs on `opened`,
`synchronize` and `reopened`.

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

Layout and conventions for contributors (human or AI) are in `AGENTS.md`.
