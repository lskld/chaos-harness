import json
import os
import stat
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

    def test_example_config_is_written_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "config.json"
            with self.assertRaises(config_mod.ConfigError):
                config_mod.load(path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)

    def test_save_writes_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            config_mod.save(path, SAMPLE)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)

    def test_load_tightens_group_or_world_readable_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(SAMPLE), encoding="utf-8")
            os.chmod(path, 0o644)
            cfg = config_mod.load(path)
            self.assertEqual(cfg["default_model"], "openrouter/auto")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)

    def test_save_tightens_existing_loose_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps(SAMPLE), encoding="utf-8")
            os.chmod(path, 0o640)
            config_mod.save(path, SAMPLE)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)

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


    def test_secrets_collects_api_keys_recursively(self):
        cfg = {
            "providers": {
                "p": {"api_key": "sk-aaaabbbb1111"},
                "q": {"api_key": "sk-ccccdddd2222"},
            },
            "search": {"api_key": "sk-eeeeffff3333"},
            "default_model": "p/m",
        }
        self.assertEqual(
            sorted(config_mod.secrets(cfg)),
            ["sk-aaaabbbb1111", "sk-ccccdddd2222", "sk-eeeeffff3333"],
        )
        self.assertEqual(config_mod.secrets(SAMPLE), ("sk-test", "gsk-test"))

    def test_redact_replaces_long_secrets_and_skips_short_ones(self):
        self.assertEqual(
            config_mod.redact("key sk-aaaabbbb1111 here", ("sk-aaaabbbb1111",)),
            "key ***redacted*** here",
        )
        self.assertEqual(config_mod.redact("abc abc", ("abc",)), "abc abc")


if __name__ == "__main__":
    unittest.main()
