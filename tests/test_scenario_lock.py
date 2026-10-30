"""Filesystem and subprocess regression tests for persistent local sandbox exclusion."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.scenario_lock import acquire_sandbox_lock, release_sandbox_lock
from research.sandbox_readiness import BUCKET

RUN = "a" * 32


class ScenarioLockTests(unittest.TestCase):
    """Keep interrupted or mismatched runs from silently clearing local execution locks."""

    def test_matching_release_and_reacquire(self):
        """Verify exclusion, private modes and explicit successful release.

        Inputs:
            self: Test instance using a temporary private directory.
        Outputs:
            None; creates and removes synthetic filesystem locks, never calls AWS.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock = acquire_sandbox_lock(root, RUN)
            self.assertEqual(lock.stat().st_mode & 0o777, 0o700)
            self.assertEqual((lock / "owner.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                acquire_sandbox_lock(root, "b" * 32)
            release_sandbox_lock(root, RUN)
            acquire_sandbox_lock(root, "b" * 32)
            release_sandbox_lock(root, "b" * 32)

    def test_subprocess_exit_keeps_lock(self):
        """An exited owner process must leave reuse blocked rather than imply restoration.

        Inputs:
            self: Test instance launching an offline child in the current Python environment.
        Outputs:
            None; asserts a persistent marker after normal child exit and rejects takeover.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            result = subprocess.run([sys.executable, "-c",
                "import sys; from research.scenario_lock import acquire_sandbox_lock; acquire_sandbox_lock(sys.argv[1], sys.argv[2])",
                str(root), RUN], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaises(FileExistsError):
                acquire_sandbox_lock(root, RUN)
            release_sandbox_lock(root, RUN)

    def test_wrong_owner_partial_and_unexpected_files_block_release(self):
        """Keep mismatched owner records and incomplete or expanded lock directories intact.

        Inputs:
            self: Test instance constructing independent private synthetic lock states.
        Outputs:
            None; asserts no failed release silently removes the lock directory.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock = acquire_sandbox_lock(root, RUN)
            with self.assertRaises(ValueError):
                release_sandbox_lock(root, "b" * 32)
            (lock / "extra").write_text("synthetic")
            with self.assertRaises(ValueError):
                release_sandbox_lock(root, RUN)
            (lock / "extra").unlink()
            (lock / "owner.json").unlink()
            with self.assertRaises(ValueError):
                release_sandbox_lock(root, RUN)
            with self.assertRaises(FileExistsError):
                acquire_sandbox_lock(root, RUN)
            self.assertTrue(lock.is_dir())

    def test_links_permissions_and_path_identifiers_rejected(self):
        """Reject shared roots, symlinked markers and path-like owner identifiers.

        Inputs:
            self: Test instance varying temporary filesystem modes and synthetic names.
        Outputs:
            None; asserts filesystem scope failures and preserves the linked target.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(ValueError):
                acquire_sandbox_lock(root, "../other")
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                acquire_sandbox_lock(root, RUN)
            root.chmod(0o700)
            lock = acquire_sandbox_lock(root, RUN)
            (lock / "owner.json").unlink()
            target = root / "target"
            target.write_text("untouched")
            (lock / "owner.json").symlink_to(target)
            with self.assertRaises(OSError):
                release_sandbox_lock(root, RUN)
            self.assertEqual(target.read_text(), "untouched")
