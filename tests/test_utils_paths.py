import tempfile
import unittest
from pathlib import Path

from utils.paths import (
    display_path_relative_to_cwd,
    ensure_parent_dir,
    is_binary_file,
    resolve_path,
)


class ResolvePathTests(unittest.TestCase):
    """resolve_path is the containment gate: everything it returns is inside base."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)

    def test_joins_a_relative_path_onto_base(self):
        self.assertEqual(resolve_path(self.base, "src/main.py"), self.base / "src" / "main.py")

    def test_accepts_an_absolute_path_inside_base(self):
        inside = self.base / "src" / "main.py"
        self.assertEqual(resolve_path(self.base, inside), inside)

    def test_rejects_a_traversal_out_of_base(self):
        with self.assertRaises(ValueError) as caught:
            resolve_path(self.base, "../escaped.txt")
        self.assertIn("outside the working directory", str(caught.exception))

    def test_rejects_a_traversal_that_dips_back_out(self):
        with self.assertRaises(ValueError):
            resolve_path(self.base, "src/../../escaped.txt")

    def test_rejects_an_absolute_path_outside_base(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(ValueError):
                resolve_path(self.base, Path(other) / "file.txt")

    def test_base_itself_is_inside_base(self):
        self.assertEqual(resolve_path(self.base, "."), self.base)

    def test_a_sibling_sharing_the_name_prefix_is_still_outside(self):
        # `<base>-evil` starts with the same characters as `<base>`, so a string
        # prefix check would let it through. relative_to does not.
        sibling = Path(f"{self.base}-evil") / "file.txt"
        with self.assertRaises(ValueError):
            resolve_path(self.base, sibling)


class DisplayPathTests(unittest.TestCase):
    # These paths are never read from disk, and pathlib anchors a leading slash
    # to the current drive on Windows, so one literal works on both platforms.
    def test_relative_to_cwd_when_underneath_it(self):
        cwd = Path("/home/user/project")
        shown = display_path_relative_to_cwd(str(cwd / "src" / "main.py"), cwd)
        self.assertEqual(Path(shown), Path("src/main.py"))

    def test_falls_back_to_the_full_path_when_outside_cwd(self):
        cwd = Path("/home/user/project")
        other = Path("/etc/hosts")
        self.assertEqual(display_path_relative_to_cwd(str(other), cwd), str(other))

    def test_passes_the_path_through_when_there_is_no_cwd(self):
        self.assertEqual(display_path_relative_to_cwd("some/where.py", None), str(Path("some/where.py")))


class IsBinaryFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_null_byte_makes_it_binary(self):
        target = self.dir / "payload.bin"
        target.write_bytes(b"MZ\x00\x90")
        self.assertTrue(is_binary_file(target))

    def test_plain_text_is_not_binary(self):
        target = self.dir / "notes.txt"
        target.write_text("just words\nand more words\n", encoding="utf-8")
        self.assertFalse(is_binary_file(target))

    def test_only_the_first_chunk_is_read(self):
        # A NUL past the 8192-byte window is not seen, which is the documented
        # cost of sniffing a fixed prefix rather than the whole file.
        target = self.dir / "late.bin"
        target.write_bytes(b"a" * 9000 + b"\x00")
        self.assertFalse(is_binary_file(target))

    def test_a_missing_file_is_not_binary(self):
        self.assertFalse(is_binary_file(self.dir / "does-not-exist"))


class EnsureParentDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_creates_every_missing_parent_and_returns_the_path(self):
        target = self.dir / "a" / "b" / "c" / "file.txt"
        returned = ensure_parent_dir(target)
        self.assertEqual(returned, target)
        self.assertTrue(target.parent.is_dir())
        self.assertFalse(target.exists())

    def test_is_a_no_op_when_the_parent_is_already_there(self):
        target = self.dir / "file.txt"
        ensure_parent_dir(target)
        ensure_parent_dir(target)
        self.assertTrue(self.dir.is_dir())


if __name__ == "__main__":
    unittest.main()
