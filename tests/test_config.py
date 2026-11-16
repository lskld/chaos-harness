import json
import tempfile
import unittest
from pathlib import Path

from chaos import config as config_mod

SAMPLE = {
    "default_model": "openrouter/auto",
    "providers": {
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
            "models": ["auto", "anthropic/claude-sonnet-4.5"],
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk-test",
            "models": ["llama-3.3-70b-versatile"],
        },
    },
    "theme": {"assistant": "magenta"},
}


def load_sample(directory):
    path = Path(directory) / "config.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return config_mod.load(path)


class ConfigTest(unittest.TestCase):
    def test_missing_config_writes_example(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "config.json"
            with self.assertRaises(config_mod.ConfigError):
                config_mod.load(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("providers", data)

    def test_resolve_provider_model(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        base_url, api_key, model = config_mod.resolve(cfg, "groq/llama-3.3-70b-versatile")
        self.assertEqual(
            (base_url, api_key, model),
            ("https://api.groq.com/openai/v1", "gsk-test", "llama-3.3-70b-versatile"),
        )

    def test_resolve_uses_default_model(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        self.assertEqual(config_mod.resolve(cfg, None)[2], "auto")

    def test_resolve_unknown_provider(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(cfg, "nope/auto")

    def test_resolve_bad_format_lists_models(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        with self.assertRaises(config_mod.ConfigError) as ctx:
            config_mod.resolve(cfg, "auto")
        self.assertIn("openrouter/auto", str(ctx.exception))

    def test_list_models(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        self.assertEqual(
            sorted(config_mod.list_models(cfg)),
            [
                "groq/llama-3.3-70b-versatile",
                "openrouter/anthropic/claude-sonnet-4.5",
                "openrouter/auto",
            ],
        )

    def test_theme_merges_with_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        theme = config_mod.theme(cfg)
        self.assertEqual(theme["assistant"], "magenta")
        self.assertEqual(theme["prompt"], config_mod.DEFAULT_THEME["prompt"])
        self.assertEqual(theme["background"], config_mod.DEFAULT_THEME["background"])

    def test_theme_selection_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_sample(d)
        self.assertEqual(config_mod.theme(cfg, "ocean")["background"], "#0a1420")
        self.assertEqual(
            config_mod.theme(cfg)["background"], config_mod.DEFAULT_THEME["background"]
        )
        self.assertIn("fire", config_mod.theme_names())
        cfg["theme_name"] = "mono"
        self.assertEqual(config_mod.theme(cfg)["background"], "#111111")


if __name__ == "__main__":
    unittest.main()
