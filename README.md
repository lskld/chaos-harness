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
}
```

Fill in one `providers` block per API you want to use: `base_url` is the API
root, `api_key` its key, `models` the model IDs it serves. Set `default_model`
to `"my-provider/<model-id>"`, or pick a model per run with `--model
provider/model` or the `/model` command inside the CLI. Adding a provider block
makes all of its models available immediately. Colors are customizable via the
`theme` block.

`chaos` takes over the whole terminal (alternate screen): a top bar with the
current model and an evil fireball mascot top-right — while the model thinks it
bobs up and down, cycles thinking faces, and shows a `thinking…` spinner line below
it. Below that: a scrollable chat (your prompts, the model's reasoning when the
provider returns it, replies as markdown) and an input line docked at the bottom.
Commands: `/help` (lists them all), `/exit` (or ctrl+q), `/clear`,
`/model [provider/model]`, `/theme`.
`/theme` opens a menu you navigate with ↑/↓ + enter (esc closes). Built-in themes:
`fire` (default), `ocean`, `forest`, `sunset`, `mono` — switching re-themes the
whole app live; `/theme ocean` also works directly, and `"theme_name": "ocean"`
in the config preselects one. When stdin is piped it falls back to a plain print
loop; `chaos "prompt"` stays one-shot and pipe-friendly.

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

Layout and conventions for contributors (human or AI) are in `AGENTS.md`.
