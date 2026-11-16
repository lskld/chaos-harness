# chaos-harness

A hackathon-specific, bring-your-own-model agent CLI, made by Team Chaos — free
for anyone to use, fork, and adapt.

## Quickstart

```bash
pip install -e .
chaos          # first run writes an example ~/.chaos/config.json — add a provider + API key
chaos "hi"     # one-shot prompt
```

## Config (`~/.chaos/config.json`)

```json
{
  "default_model": "openrouter/auto",
  "providers": {
    "openrouter": {
      "base_url": "https://openrouter.ai/api/v1",
      "api_key": "sk-or-...",
      "models": ["auto", "anthropic/claude-sonnet-4.5"]
    }
  },
  "theme": {
    "prompt": "bold cyan",
    "user": "bold white",
    "assistant": "green",
    "error": "bold red",
    "info": "dim"
  }
}
```

Every provider is called through the OpenAI-compatible `POST /chat/completions`
endpoint, so adding one block makes all of its models available. Pick a model with
`--model provider/model` or the `/model` command inside the CLI. Colors are
customizable via the `theme` block.

Inside the CLI: `/exit`, `/clear`, `/model [provider/model]`.

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

Layout and conventions for contributors (human or AI) are in `AGENTS.md`.
