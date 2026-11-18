import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chaos import tools
from chaos.tools import ToolContext, ToolError, execute, open_checked, resolve_path, schemas


class RegistryTest(unittest.TestCase):
    def test_schemas_cover_the_file_tools(self):
        names = {entry["function"]["name"] for entry in schemas()}
        self.assertEqual(names, {"read_file", "list_files", "edit_file", "write_file"})
        for entry in schemas():
            self.assertEqual(entry["type"], "function")
            self.assertIn("parameters", entry["function"])

    def test_execute_unknown_tool_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            result = json.loads(execute("nope", "{}", ctx))
        self.assertFalse(result["ok"])
        self.assertIn("unknown tool", result["error"])

    def test_execute_invalid_json_arguments_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            result = json.loads(execute("read_file", "{not json", ctx))
        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON arguments", result["error"])

    def test_execute_non_object_arguments_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            result = json.loads(execute("read_file", "[1, 2]", ctx))
        self.assertFalse(result["ok"])
        self.assertIn("JSON object", result["error"])

    def test_execute_wraps_unexpected_handler_errors(self):
        class Boom(Exception):
            pass

        def handler(args, ctx):
            raise Boom("kaput")

        tools._BY_NAME["boom"] = tools.Tool("boom", "", {}, handler)
        try:
            with tempfile.TemporaryDirectory() as d:
                ctx = ToolContext(root=Path(d))
                result = json.loads(execute("boom", "{}", ctx))
            self.assertFalse(result["ok"])
            self.assertIn("kaput", result["error"])
        finally:
            del tools._BY_NAME["boom"]

    def test_execute_redacts_secrets_from_results(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "f.txt").write_text("token sk-aaaabbbb1111 leaked", encoding="utf-8")
            ctx = ToolContext(root=Path(d), secrets=("sk-aaaabbbb1111",))
            result = json.loads(execute("read_file", json.dumps({"path": "f.txt"}), ctx))
        self.assertTrue(result["ok"])
        self.assertNotIn("sk-aaaabbbb1111", result["content"])
        self.assertIn("***redacted***", result["content"])

    def test_execute_redacts_secrets_from_error_messages(self):
        def handler(args, ctx):
            raise RuntimeError("boom sk-aaaabbbb1111")

        tools._BY_NAME["leak"] = tools.Tool("leak", "", {}, handler)
        try:
            with tempfile.TemporaryDirectory() as d:
                ctx = ToolContext(root=Path(d), secrets=("sk-aaaabbbb1111",))
                result = json.loads(execute("leak", "{}", ctx))
            self.assertFalse(result["ok"])
            self.assertNotIn("sk-aaaabbbb1111", result["error"])
            self.assertIn("***redacted***", result["error"])
        finally:
            del tools._BY_NAME["leak"]

    def test_execute_truncates_oversized_results(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "big.txt").write_text("x" * 5000, encoding="utf-8")
            ctx = ToolContext(root=Path(d), max_result_bytes=200)
            result = execute("read_file", json.dumps({"path": "big.txt"}), ctx)
        self.assertLessEqual(len(result), 200 + 60)
        self.assertIn("truncated", result)


class ResolvePathTest(unittest.TestCase):
    def test_relative_path_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            self.assertEqual(resolve_path(ctx, "a/b.txt"), (Path(d) / "a" / "b.txt").resolve())

    def test_dotdot_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            with self.assertRaises(ToolError):
                resolve_path(ctx, "../outside.txt")

    def test_absolute_path_outside_root_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            with self.assertRaises(ToolError):
                resolve_path(ctx, "/etc/passwd")

    def test_symlink_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            outside = Path(d) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            (root / "link.txt").symlink_to(outside)
            ctx = ToolContext(root=root)
            with self.assertRaises(ToolError):
                resolve_path(ctx, "link.txt")

    def test_empty_path_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            with self.assertRaises(ToolError):
                resolve_path(ctx, "   ")

    def test_protected_dirs_are_refused_regardless_of_root(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            for raw in (".chaos/config.json", ".ssh/id_rsa", ".aws/credentials", "sub/.gnupg/gpg.conf"):
                with self.assertRaises(ToolError) as cm:
                    resolve_path(ctx, raw)
                self.assertIn("protected directory", str(cm.exception))

    def test_other_dot_directories_are_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d))
            resolved = resolve_path(ctx, ".github/workflows/ci.yml")
            self.assertEqual(resolved, (Path(d) / ".github" / "workflows" / "ci.yml").resolve())


class WorkspaceRootTest(unittest.TestCase):
    def test_workspace_root_defaults_to_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("os.getcwd", return_value=d):
                self.assertEqual(tools.workspace_root({}), Path(d).resolve())

    def test_workspace_root_comes_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                tools.workspace_root({"workspace_root": str(Path(d) / "proj")}),
                (Path(d) / "proj").resolve(),
            )

    def test_root_warning_when_root_is_home(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            with patch("pathlib.Path.home", return_value=home):
                warning = tools.root_warning(home, home / ".chaos" / "config.json")
            self.assertIsNotNone(warning)
            self.assertIn(str(home), warning)
            self.assertIn("workspace_root", warning)

    def test_root_warning_when_root_is_an_ancestor_of_home(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            with patch("pathlib.Path.home", return_value=home):
                warning = tools.root_warning(Path(d), home / ".chaos" / "config.json")
            self.assertIsNotNone(warning)

    def test_root_warning_when_config_dir_is_inside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            with patch("pathlib.Path.home", return_value=Path(d) / "home"):
                warning = tools.root_warning(root, root / ".chaos" / "config.json")
            self.assertIsNotNone(warning)

    def test_no_warning_for_a_plain_project_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            with patch("pathlib.Path.home", return_value=Path(d) / "home"):
                warning = tools.root_warning(root, Path(d) / "home" / ".chaos" / "config.json")
            self.assertIsNone(warning)


class OpenCheckedTest(unittest.TestCase):
    def test_opens_a_normal_file_inside_the_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            target = root / "f.txt"
            target.write_text("ok", encoding="utf-8")
            ctx = ToolContext(root=root)
            fd = open_checked(ctx, target, os.O_RDONLY)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "ok")

    def test_refuses_path_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ToolContext(root=Path(d) / "root")
            with self.assertRaises(ToolError) as cm:
                open_checked(ctx, Path(d) / "outside.txt", os.O_RDONLY)
            self.assertIn("outside the workspace root", str(cm.exception))

    def test_refuses_protected_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            (root / ".ssh").mkdir(parents=True)
            target = root / ".ssh" / "id_rsa"
            target.write_text("key", encoding="utf-8")
            ctx = ToolContext(root=root)
            with self.assertRaises(ToolError) as cm:
                open_checked(ctx, target, os.O_RDONLY)
            self.assertIn("protected directory", str(cm.exception))

    def test_refuses_symlink_swapped_in_before_open(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            outside = Path(d) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            victim = root / "victim.txt"
            victim.write_text("ok", encoding="utf-8")
            ctx = ToolContext(root=root)
            real_open = os.open

            def racing_open(path, flags, mode=0o777, **kwargs):
                if Path(path) == victim:
                    victim.unlink()
                    victim.symlink_to(outside)
                return real_open(path, flags, mode, **kwargs)

            with patch("os.open", side_effect=racing_open):
                with self.assertRaises(ToolError):
                    open_checked(ctx, victim, os.O_RDONLY)

    @unittest.skipUnless(Path("/proc/self/fd").exists(), "needs /proc/self/fd")
    def test_refuses_parent_dir_swapped_to_symlink_before_open(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            (root / "sub").mkdir(parents=True)
            victim = root / "sub" / "f.txt"
            victim.write_text("ok", encoding="utf-8")
            outside = Path(d) / "outside"
            outside.mkdir()
            (outside / "f.txt").write_text("secret", encoding="utf-8")
            ctx = ToolContext(root=root)
            real_open = os.open

            def racing_open(path, flags, mode=0o777, **kwargs):
                if Path(path) == victim:
                    (root / "sub").rename(root / "sub_real")
                    (root / "sub").symlink_to(outside)
                return real_open(path, flags, mode, **kwargs)

            with patch("os.open", side_effect=racing_open):
                with self.assertRaises(ToolError) as cm:
                    open_checked(ctx, victim, os.O_RDONLY)
            self.assertIn("escaped the workspace root", str(cm.exception))
            self.assertEqual((outside / "f.txt").read_text(encoding="utf-8"), "secret")


if __name__ == "__main__":
    unittest.main()
