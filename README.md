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
    "prompt": "bold cyan",
    "user": "bold white",
    "assistant": "green",
    "error": "bold red",
    "info": "dim",
    "banner": "bold bright_yellow",
    "thinking": "dim italic"
  }
}
```

Fill in one `providers` block per API you want to use: `base_url` is the API
root, `api_key` its key, `models` the model IDs it serves. Set `default_model`
to `"my-provider/<model-id>"`, or pick a model per run with `--model
provider/model` or the `/model` command inside the CLI. Adding a provider block
makes all of its models available immediately. Colors are customizable via the
`theme` block.

`chaos` takes over the whole terminal (alternate screen): a fireball top bar with
the current model, a scrollable chat — your prompts, the model's thinking when the
provider returns it, and replies as rendered panels — and an input line docked at
the bottom. Commands: `/exit` (or ctrl+q), `/clear`, `/model [provider/model]`.
When stdin is piped it falls back to a plain print loop; `chaos "prompt"` stays
one-shot and pipe-friendly.

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

Layout and conventions for contributors (human or AI) are in `AGENTS.md`.
