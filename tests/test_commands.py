import unittest

from chaos import commands

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}


class SplitTest(unittest.TestCase):
    def test_plain_text_is_not_a_command(self):
        self.assertEqual(commands.split("hello there"), (None, ""))

    def test_command_without_arg(self):
        self.assertEqual(commands.split("/model"), ("/model", ""))

    def test_command_with_arg(self):
        self.assertEqual(commands.split("/theme ocean"), ("/theme", "ocean"))
        self.assertEqual(commands.split("  /model  p/m2 "), ("/model", "p/m2"))

    def test_unknown_slash_word_is_not_a_known_command(self):
        name, _ = commands.split("/foo")
        self.assertNotIn(name, commands.COMMANDS)


class ModelCommandTest(unittest.TestCase):
    def test_lists_models_with_marker(self):
        ref, out = commands.model_command(CFG, "", "p/m")
        self.assertEqual(ref, "p/m")
        self.assertEqual(out, [("info", "* p/m"), ("info", "  p/m2")])

    def test_switches_valid_model(self):
        ref, out = commands.model_command(CFG, "p/m2", "p/m")
        self.assertEqual(ref, "p/m2")
        self.assertEqual(out, [("info", "switched to p/m2")])

    def test_rejects_unknown_model(self):
        ref, out = commands.model_command(CFG, "nope/m", "p/m")
        self.assertEqual(ref, "p/m")
        self.assertEqual(out[0][0], "error")


class ThemeCommandTest(unittest.TestCase):
    def test_lists_themes_with_marker(self):
        name, out = commands.theme_command("", "fire")
        self.assertIsNone(name)
        self.assertEqual(out[0], ("info", "* fire"))
        self.assertTrue(any("ocean" in text for _, text in out))

    def test_accepts_known_theme(self):
        self.assertEqual(commands.theme_command("ocean", "fire"), ("ocean", []))

    def test_rejects_unknown_theme(self):
        name, out = commands.theme_command("nope", "fire")
        self.assertIsNone(name)
        self.assertEqual(out[0][0], "error")
        self.assertIn("unknown theme", out[0][1])


if __name__ == "__main__":
    unittest.main()
