import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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

    def test_load_raises_config_error_when_config_dir_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(config_mod.ConfigError) as ctx:
                config_mod.load(blocker / "config.json")
            self.assertIn("cannot write example config", str(ctx.exception))

    def test_load_raises_config_error_when_example_config_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            with patch("chaos.config._write_private", side_effect=OSError("read-only file system")):
                with self.assertRaises(config_mod.ConfigError) as ctx:
                    config_mod.load(path)
            self.assertIn("cannot write example config", str(ctx.exception))
            self.assertIn("read-only file system", str(ctx.exception))

    def test_example_config_uses_theme_name_not_a_filled_theme_block(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "config.json"
            with self.assertRaises(config_mod.ConfigError):
                config_mod.load(path)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("theme", data)
        self.assertEqual(data["theme_name"], config_mod.DEFAULT_THEME_NAME)
        self.assertEqual(config_mod.theme(data, "ocean")["background"], "#0a1420")

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


class DeadlineTest(unittest.TestCase):
    def test_resolve_deadline_same_day(self):
        now = datetime(2026, 11, 19, 9, 30)
        parsed = datetime.fromisoformat(config_mod.resolve_deadline("17:00", now=now))
        self.assertEqual(
            (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second),
            (2026, 11, 19, 17, 0, 0),
        )
        self.assertIsNotNone(parsed.tzinfo)

    def test_resolve_deadline_next_day_when_already_past(self):
        now = datetime(2026, 11, 19, 18, 0)
        parsed = datetime.fromisoformat(config_mod.resolve_deadline("17:00", now=now))
        self.assertEqual((parsed.day, parsed.hour, parsed.minute), (20, 17, 0))
        exactly = datetime(2026, 11, 19, 17, 0)
        parsed = datetime.fromisoformat(config_mod.resolve_deadline("17:00", now=exactly))
        self.assertEqual(parsed.day, 20)

    def test_resolve_deadline_accepts_seconds(self):
        now = datetime(2026, 11, 19, 9, 0)
        parsed = datetime.fromisoformat(config_mod.resolve_deadline("17:00:30", now=now))
        self.assertEqual(parsed.second, 30)

    def test_resolve_deadline_off_and_clear(self):
        self.assertIsNone(config_mod.resolve_deadline("off"))
        self.assertIsNone(config_mod.resolve_deadline(" clear "))

    def test_resolve_deadline_rejects_invalid_input(self):
        for bad in ("", "soon", "25:00", "17:5", "17:00:99"):
            with self.assertRaises(config_mod.ConfigError) as ctx:
                config_mod.resolve_deadline(bad)
            self.assertIn("HH:MM", str(ctx.exception))

    def test_deadline_text_shows_floored_remaining(self):
        now = datetime(2026, 11, 19, 12, 0)
        iso = config_mod.resolve_deadline("17:00", now=now)
        self.assertEqual(config_mod.deadline_text({"deadline": iso}, now=now), "⏳ 5:00 left")
        later = now + timedelta(hours=2, minutes=30, seconds=59)
        self.assertEqual(config_mod.deadline_text({"deadline": iso}, now=later), "⏳ 2:29 left")

    def test_deadline_text_hidden_when_unset_invalid_or_expired(self):
        now = datetime(2026, 11, 19, 12, 0)
        self.assertEqual(config_mod.deadline_text({}, now=now), "")
        self.assertEqual(config_mod.deadline_text({"deadline": "not-a-date"}, now=now), "")
        past = (now - timedelta(minutes=1)).astimezone().isoformat(timespec="seconds")
        self.assertEqual(config_mod.deadline_text({"deadline": past}, now=now), "")

    def test_deadline_context_when_active_and_shrinking(self):
        now = datetime(2026, 11, 19, 12, 0)
        iso = config_mod.resolve_deadline("17:00", now=now)
        cfg = {"deadline": iso}
        line = config_mod.deadline_context(cfg, now=now)
        self.assertIn("Hackathon deadline:", line)
        self.assertIn("5:00 remaining", line)
        later = now + timedelta(hours=2, minutes=30)
        self.assertIn("2:30 remaining", config_mod.deadline_context(cfg, now=later))

    def test_deadline_context_hidden_when_unset_invalid_or_expired(self):
        now = datetime(2026, 11, 19, 12, 0)
        self.assertEqual(config_mod.deadline_context({}, now=now), "")
        self.assertEqual(config_mod.deadline_context({"deadline": "junk"}, now=now), "")
        past = (now - timedelta(minutes=1)).astimezone().isoformat(timespec="seconds")
        self.assertEqual(config_mod.deadline_context({"deadline": past}, now=now), "")

    def test_deadline_survives_config_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            cfg = dict(SAMPLE, deadline="2026-11-19T17:00:00+01:00")
            config_mod.save(path, cfg)
            self.assertEqual(config_mod.load(path)["deadline"], "2026-11-19T17:00:00+01:00")


if __name__ == "__main__":
    unittest.main()
