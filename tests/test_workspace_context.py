"""File Explorer policy and Git evidence against a disposable repository."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestra.core import Invalid
from orchestra.project_files import (
    browse_project,
    project_file_diff,
    project_file_visible,
    project_git_status,
    read_project_file,
    search_project_files,
)
from orchestra.remote import MAX_FILE


class ProjectExplorerTest(unittest.TestCase):
    def test_secret_names_and_unsafe_relative_paths_are_excluded(self):
        for name in (
            "../outside", ".git/config", "dir/../file", "\\host\\file", ".env", "src/.env.local",
            "secret.json", "nested/.aws/config", "nested/.SSH/config", ".codex/auth.json", "auth.sqlite", "cert.p12",
        ):
            with self.subTest(name=name):
                self.assertFalse(project_file_visible(name))
        self.assertTrue(project_file_visible("docs/프로젝트 상태.md"))
        self.assertTrue(project_file_visible("src/authentication.py"))

    def test_directory_navigation_search_and_preview_use_same_boundary(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-context-") as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            folder = root / "문서 folder"
            folder.mkdir()
            (folder / "계획.md").write_text("통합 워크스페이스", encoding="utf-8")
            (folder / ".env").write_text("PRIVATE_FIXTURE", encoding="utf-8")
            (root / "large.txt").write_bytes(b"a" * (MAX_FILE + 1))
            outside = Path(temporary) / "other"
            outside.mkdir()
            (outside / "파일.txt").write_text("OUTSIDE_REPOSITORY", encoding="utf-8")
            linked = root / "alias"
            try:
                linked.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                may_test_link = False
            else:
                may_test_link = True

            self.assertEqual(browse_project(root), ([("문서 folder", True), ("large.txt", False)], False))
            expected = [("문서 folder/계획.md", False)]
            self.assertEqual(browse_project(root, "문서 folder"), (expected, False))
            self.assertEqual(search_project_files(root, "계획"), (expected, False))
            self.assertEqual(search_project_files(root, ".env"), ([], False))
            self.assertEqual(read_project_file(root, "문서 folder/계획.md").decode(), "통합 워크스페이스")
            for name in (".git/config", "문서 folder/.env", "large.txt"):
                with self.assertRaises(Invalid):
                    read_project_file(root, name)
            if may_test_link:
                with self.assertRaises(Invalid):
                    read_project_file(root, "alias/파일.txt")

    @unittest.skipUnless(shutil.which("git"), "Git fixture")
    def test_git_status_distinguishes_staged_unstaged_and_private_files(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-context-git-") as temporary:
            root = Path(temporary)

            def git(*args):
                return subprocess.run(["git", "-C", temporary, *args], check=True, capture_output=True).stdout

            git("init", "-q", "-b", "main")
            originals = {
                "tracked file.md": "base\n", "deleted.txt": "removed\n", "staged deletion.txt": "old version\n",
                ".env": "PRIVATE_BASE\n",
            }
            for name, value in originals.items():
                (root / name).write_text(value, encoding="utf-8")
            git("add", "--", *originals)
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "initial")
            (root / "tracked file.md").write_text("indexed\n", encoding="utf-8")
            (root / "added.txt").write_text("added\n", encoding="utf-8")
            git("add", "tracked file.md", "added.txt")
            (root / "tracked file.md").write_text("working\n", encoding="utf-8")
            (root / "deleted.txt").unlink()
            git("rm", "staged deletion.txt")
            (root / ".env").write_text("PRIVATE_MODIFICATION\n", encoding="utf-8")
            (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")

            branch, rows = project_git_status(root)
            self.assertEqual(branch, "main")
            self.assertEqual(rows, {
                "tracked file.md": "MM", "added.txt": "A ", "deleted.txt": " D", "staged deletion.txt": "D ", "untracked.txt": "??",
            })
            before = git("status", "--porcelain")
            for name, evidence in {
                "tracked file.md": ("HEAD → Index", "Index → Worktree", "+indexed", "+working", "-base"),
                "added.txt": ("+added",),
                "deleted.txt": ("-removed",),
                "staged deletion.txt": ("HEAD → Index", "-old version"),
                "untracked.txt": ("+untracked",),
            }.items():
                with self.subTest(name=name):
                    diff = project_file_diff(root, name, rows[name])
                    for line in evidence:
                        self.assertIn(line, diff)
            self.assertEqual(git("status", "--porcelain"), before)
            with self.assertRaises(Invalid):
                project_file_diff(root, ".env", " M")


if __name__ == "__main__":
    unittest.main()
