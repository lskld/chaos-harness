import json
import tempfile
import unittest
from pathlib import Path

from chaos import tools
from chaos.tools import ToolContext, ToolError, execute, resolve_path, schemas


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


if __name__ == "__main__":
    unittest.main()
