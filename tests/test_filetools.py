import json
import tempfile
import unittest
from pathlib import Path

from chaos.tools import ToolContext, execute


class FileToolsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ctx = ToolContext(root=self.root)
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        (self.root / "README.md").write_text("# hi\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def call(self, name, args):
        return json.loads(execute(name, json.dumps(args), self.ctx))

    def test_read_file_returns_lines(self):
        result = self.call("read_file", {"path": "src/a.py"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "alpha\nbeta\ngamma")
        self.assertEqual(result["total_lines"], 3)
        self.assertEqual(result["path"], "src/a.py")

    def test_read_file_offset_and_limit(self):
        result = self.call("read_file", {"path": "src/a.py", "offset": 2, "limit": 1})
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "beta")

    def test_read_file_missing_file(self):
        result = self.call("read_file", {"path": "nope.txt"})
        self.assertFalse(result["ok"])
        self.assertIn("not a file", result["error"])

    def test_read_file_outside_root(self):
        result = self.call("read_file", {"path": "../secret.txt"})
        self.assertFalse(result["ok"])
        self.assertIn("outside the workspace root", result["error"])

    def test_read_file_refuses_binary(self):
        (self.root / "bin.dat").write_bytes(b"PK\x00\x01binary")
        result = self.call("read_file", {"path": "bin.dat"})
        self.assertFalse(result["ok"])
        self.assertIn("binary", result["error"])

    def test_read_file_over_size_limit_reads_only_the_head(self):
        (self.root / "big.log").write_text("line\n" * 5000, encoding="utf-8")
        ctx = ToolContext(root=self.root, max_file_bytes=1000)
        result = json.loads(execute("read_file", json.dumps({"path": "big.log"}), ctx))
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["content"].encode("utf-8")), 1000)
        self.assertEqual(result["total_lines"], 5000)

    def test_read_file_over_size_limit_still_applies_offset_and_limit(self):
        (self.root / "big.log").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        ctx = ToolContext(root=self.root, max_file_bytes=6)
        result = json.loads(execute("read_file", json.dumps({"path": "big.log", "offset": 2, "limit": 2}), ctx))
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["content"], "b\nc")
        self.assertEqual(result["total_lines"], 5)

    def test_read_file_over_size_limit_refuses_binary(self):
        (self.root / "big.bin").write_bytes(b"PK\x00\x03" + b"x" * 5000)
        ctx = ToolContext(root=self.root, max_file_bytes=100)
        result = json.loads(execute("read_file", json.dumps({"path": "big.bin"}), ctx))
        self.assertFalse(result["ok"])
        self.assertIn("binary", result["error"])

    def test_list_files_lists_and_filters(self):
        result = self.call("list_files", {"path": "."})
        self.assertTrue(result["ok"])
        self.assertEqual(result["files"], ["README.md", "src/a.py"])
        result = self.call("list_files", {"path": ".", "pattern": "*.py"})
        self.assertEqual(result["files"], ["src/a.py"])

    def test_protected_dirs_are_refused_by_all_file_tools(self):
        (self.root / ".ssh").mkdir()
        (self.root / ".ssh" / "id_rsa").write_text("key", encoding="utf-8")
        result = self.call("read_file", {"path": ".ssh/id_rsa"})
        self.assertFalse(result["ok"])
        self.assertIn("protected directory", result["error"])
        result = self.call("edit_file", {"path": ".ssh/id_rsa", "old_str": "key", "new_str": "x"})
        self.assertFalse(result["ok"])
        self.assertIn("protected directory", result["error"])
        result = self.call("write_file", {"path": ".chaos/config.json", "content": "{}"})
        self.assertFalse(result["ok"])
        self.assertIn("protected directory", result["error"])
        self.assertFalse((self.root / ".chaos").exists())

    def test_list_files_skips_protected_dirs(self):
        (self.root / ".ssh").mkdir()
        (self.root / ".ssh" / "id_rsa").write_text("key", encoding="utf-8")
        result = self.call("list_files", {"path": "."})
        self.assertTrue(result["ok"])
        self.assertNotIn(".ssh/id_rsa", result["files"])

    def test_list_files_skips_vcs_and_cache_dirs(self):
        (self.root / ".git").mkdir()
        (self.root / ".git" / "HEAD").write_text("ref", encoding="utf-8")
        (self.root / "__pycache__").mkdir()
        (self.root / "__pycache__" / "a.cpython-311.pyc").write_bytes(b"\x00")
        result = self.call("list_files", {"path": "."})
        self.assertNotIn(".git/HEAD", result["files"])
        self.assertNotIn("__pycache__/a.cpython-311.pyc", result["files"])

    def test_list_files_missing_directory(self):
        result = self.call("list_files", {"path": "nope"})
        self.assertFalse(result["ok"])

    def test_edit_file_replaces_once_and_returns_diff(self):
        result = self.call("edit_file", {"path": "src/a.py", "old_str": "beta", "new_str": "BETA"})
        self.assertTrue(result["ok"])
        self.assertEqual((self.root / "src" / "a.py").read_text(encoding="utf-8"), "alpha\nBETA\ngamma\n")
        self.assertIn("-beta", result["diff"])
        self.assertIn("+BETA", result["diff"])

    def test_edit_file_not_found(self):
        result = self.call("edit_file", {"path": "src/a.py", "old_str": "zzz", "new_str": "x"})
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_edit_file_requires_unique_match(self):
        (self.root / "dup.txt").write_text("ab ab\n", encoding="utf-8")
        result = self.call("edit_file", {"path": "dup.txt", "old_str": "ab", "new_str": "x"})
        self.assertFalse(result["ok"])
        self.assertIn("2 times", result["error"])

    def test_edit_file_empty_old_str(self):
        result = self.call("edit_file", {"path": "src/a.py", "old_str": "", "new_str": "x"})
        self.assertFalse(result["ok"])

    def test_edit_file_outside_root(self):
        result = self.call("edit_file", {"path": "../x.txt", "old_str": "a", "new_str": "b"})
        self.assertFalse(result["ok"])
        self.assertIn("outside the workspace root", result["error"])

    def test_edit_file_over_size_limit_is_refused(self):
        ctx = ToolContext(root=self.root, max_file_bytes=5)
        result = json.loads(
            execute("edit_file", json.dumps({"path": "src/a.py", "old_str": "beta", "new_str": "x"}), ctx)
        )
        self.assertFalse(result["ok"])
        self.assertIn("over the", result["error"])

    def test_write_file_creates_with_parents(self):
        result = self.call("write_file", {"path": "new/deep/b.py", "content": "print(1)\n"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertEqual((self.root / "new" / "deep" / "b.py").read_text(encoding="utf-8"), "print(1)\n")

    def test_write_file_refuses_overwrite_without_flag(self):
        result = self.call("write_file", {"path": "README.md", "content": "x"})
        self.assertFalse(result["ok"])
        self.assertIn("overwrite=true", result["error"])
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "# hi\n")

    def test_write_file_overwrite_returns_diff(self):
        result = self.call("write_file", {"path": "README.md", "content": "# bye\n", "overwrite": True})
        self.assertTrue(result["ok"])
        self.assertFalse(result["created"])
        self.assertIn("-# hi", result["diff"])
        self.assertIn("+# bye", result["diff"])

    def test_write_file_over_size_limit_is_refused(self):
        ctx = ToolContext(root=self.root, max_file_bytes=4)
        result = json.loads(execute("write_file", json.dumps({"path": "big.txt", "content": "12345"}), ctx))
        self.assertFalse(result["ok"])
        self.assertFalse((self.root / "big.txt").exists())


if __name__ == "__main__":
    unittest.main()
