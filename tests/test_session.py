import json
import tempfile
import unittest
from pathlib import Path

from chaos import commands
from chaos.session import Session

CFG = {
    "default_model": "p/m",
    "providers": {"p": {"base_url": "https://x/v1", "api_key": "k", "models": ["m", "m2"]}},
}


def write_cfg(d, cfg=CFG):
    path = Path(d) / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


class SessionStateTest(unittest.TestCase):
    def test_defaults_come_from_cfg(self):
        session = Session({**CFG, "theme_name": "mono"}, "p/m")
        self.assertEqual(session.theme_name, "mono")
        self.assertEqual(session.theme, session.theme)
        self.assertEqual(session.messages, [])
        self.assertIsNone(session.config_path)
        session = Session(CFG, "p/m")
        self.assertNotIn("mono", session.theme_name)

    def test_cfg_is_copied_so_the_caller_dict_is_not_mutated(self):
        cfg = dict(CFG)
        session = Session(cfg, "p/m")
        session.switch_model("p/m2")
        self.assertEqual(cfg.get("default_model"), "p/m")
        self.assertEqual(session.cfg["default_model"], "p/m2")


class HandleCommandTest(unittest.TestCase):
    def test_exit_and_quit(self):
        session = Session(CFG, "p/m")
        for name in ("/exit", "/quit"):
            self.assertEqual(session.handle_command(name, ""), ("exit", []))

    def test_help_returns_the_help_lines_as_info_events(self):
        session = Session(CFG, "p/m")
        action, out = session.handle_command("/help", "")
        self.assertIsNone(action)
        self.assertEqual(out, [("info", line) for line in commands.HELP_LINES])

    def test_clear_empties_messages_and_reports_it(self):
        session = Session(CFG, "p/m")
        session.messages.append({"role": "user", "content": "hi"})
        action, out = session.handle_command("/clear", "")
        self.assertEqual(action, "clear")
        self.assertEqual(session.messages, [])
        self.assertEqual(out, [("info", "history cleared")])

    def test_unknown_command_is_a_noop(self):
        session = Session(CFG, "p/m")
        self.assertEqual(session.handle_command("/nope", ""), (None, []))

    def test_model_without_arg_asks_the_frontend_for_a_pick(self):
        session = Session(CFG, "p/m")
        self.assertEqual(session.handle_command("/model", ""), ("pick_model", []))
        action, out = session.handle_command("/model", "p/m2")
        self.assertIsNone(action)
        self.assertEqual(session.ref, "p/m2")
        self.assertEqual(out, [("info", "switched to p/m2")])

    def test_model_switch_rejects_unknown_and_keeps_ref(self):
        session = Session(CFG, "p/m")
        _, out = session.handle_command("/model", "nope/x")
        self.assertEqual(session.ref, "p/m")
        self.assertEqual(out[0][0], "error")
        self.assertIn("unknown provider", out[0][1])

    def test_theme_without_arg_asks_the_frontend_for_a_pick(self):
        session = Session(CFG, "p/m")
        self.assertEqual(session.handle_command("/theme", ""), ("pick_theme", []))
        action, out = session.handle_command("/theme", "mono")
        self.assertIsNone(action)
        self.assertEqual(session.theme_name, "mono")
        self.assertEqual(out, [])

    def test_deadline_set_off_and_invalid(self):
        session = Session(CFG, "p/m")
        _, out = session.handle_command("/deadline", "23:59")
        self.assertIn("deadline", session.cfg)
        self.assertIn("deadline set to", out[0][1])
        _, out = session.handle_command("/deadline", "off")
        self.assertNotIn("deadline", session.cfg)
        self.assertEqual(out, [("info", "deadline cleared")])
        _, out = session.handle_command("/deadline", "soon")
        self.assertEqual(out[0][0], "error")
        self.assertNotIn("deadline", session.cfg)

    def test_listings_match_the_command_helpers(self):
        session = Session(CFG, "p/m")
        self.assertEqual(session.list_models(), commands.model_command(CFG, "", "p/m")[1])
        self.assertEqual(session.list_themes(), commands.theme_command("", session.theme_name)[1])
        self.assertEqual(session.model_options(), ["p/m", "p/m2"])


class SessionPersistTest(unittest.TestCase):
    def test_switches_are_persisted_to_config_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_cfg(d)
            session = Session(CFG, "p/m", config_path=str(path))
            session.handle_command("/model", "p/m2")
            session.handle_command("/theme", "mono")
            session.handle_command("/deadline", "23:59")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["default_model"], "p/m2")
            self.assertEqual(saved["theme_name"], "mono")
            self.assertIn("deadline", saved)

    def test_no_config_path_means_no_persistence(self):
        session = Session(CFG, "p/m")
        _, out = session.handle_command("/model", "p/m2")
        self.assertEqual(session.ref, "p/m2")
        self.assertEqual([kind for kind, _ in out], ["info"])

    def test_save_failure_is_reported_as_an_error_event(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            session = Session(CFG, "p/m", config_path=str(blocker / "config.json"))
            _, out = session.handle_command("/model", "p/m2")
            self.assertEqual(session.ref, "p/m2")
            self.assertEqual(out[-1][0], "error")
            self.assertIn("could not save model to config", out[-1][1])


class RollbackToLastUserTest(unittest.TestCase):
    def test_truncates_everything_since_the_last_user_message(self):
        session = Session(CFG, "p/m")
        session.messages.extend(
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "r1"},
                {"role": "user", "content": "two"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
                {"role": "tool", "tool_call_id": "1", "name": "list_files", "content": "..."},
            ]
        )
        session.rollback_to_last_user()
        self.assertEqual(
            session.messages,
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "r1"},
            ],
        )

    def test_history_without_a_user_message_is_left_untouched(self):
        session = Session(CFG, "p/m")
        session.messages.append({"role": "system", "content": "s"})
        session.rollback_to_last_user()
        self.assertEqual(session.messages, [{"role": "system", "content": "s"}])


if __name__ == "__main__":
    unittest.main()
