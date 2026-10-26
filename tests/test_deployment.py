import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.linker as linker


class FakeState:
    def __init__(self, game):
        self.game_path = game
        self.state = {"mods": {}}
        self.saved = 0

    def save(self):
        self.saved += 1


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.mods = self.root / "mods"
        self.mods.mkdir()
        self.state = FakeState(self.game)
        patcher = patch.object(linker, "MODS_DIR", self.mods)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = linker.ModManager.__new__(linker.ModManager)
        self.manager.state_mgr = self.state

    def mod(self, name, relative="archive/pc/mod/shared.archive"):
        path = self.mods / name / relative
        path.parent.mkdir(parents=True)
        path.write_text(name)
        self.state.state["mods"][name] = {"enabled": False, "links": []}
        return path

    def test_enable_disable_restores_original(self):
        src = self.mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.parent.mkdir(parents=True)
        target.write_text("vanilla")
        self.manager.enable_mod("alpha")
        self.assertTrue(target.is_symlink())
        self.manager.disable_mod("alpha")
        self.assertEqual(target.read_text(), "vanilla")
        self.assertFalse(target.is_symlink())

    def test_conflict_does_not_replace_first_mod(self):
        src = self.mod("alpha")
        self.mod("beta")
        self.manager.enable_mod("alpha")
        with self.assertRaises(FileExistsError):
            self.manager.enable_mod("beta")
        target = self.game / src.relative_to(self.mods / "alpha")
        self.assertEqual(target.resolve(), src.resolve())
        self.assertFalse(self.state.state["mods"]["beta"]["enabled"])

    def test_disable_refuses_foreign_symlink(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        foreign = self.root / "foreign"
        foreign.write_text("foreign")
        target.symlink_to(foreign)
        with self.assertRaises(FileExistsError):
            self.manager.disable_mod("alpha")
        self.assertEqual(target.resolve(), foreign)


    def test_repair_identical_copy(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        self.assertEqual(self.manager.inspect_reconcile("alpha"),
                         [(str(src.relative_to(self.mods / "alpha")), "identical_copy")])
        self.assertEqual(len(self.manager.repair_identical_copies("alpha")), 1)
        self.assertTrue(target.is_symlink())
        self.manager.disable_mod("alpha")
        self.assertFalse(target.exists())

    def test_repair_refuses_modified_copy(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_text("user settings changed")
        with self.assertRaises(FileExistsError):
            self.manager.repair_identical_copies("alpha")
        self.assertEqual(target.read_text(), "user settings changed")

    def test_repair_rolls_back_if_symlink_fails(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        with patch.object(linker.os, "symlink", side_effect=OSError("link failed")):
            with self.assertRaises(OSError):
                self.manager.repair_identical_copies("alpha")
        self.assertEqual(target.read_bytes(), src.read_bytes())
        self.assertFalse(target.is_symlink())

    def test_repair_restores_identical_copy_and_missing_target(self):
        src = self.mod("alpha")
        extra = self.mod_extra("alpha", "archive/pc/mod/second.archive")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        other = self.game / extra.relative_to(self.mods / "alpha")
        other.unlink()
        self.assertEqual(len(self.manager.repair_identical_copies("alpha")), 2)
        self.assertTrue(target.is_symlink())
        self.assertTrue(other.is_symlink())

    def test_repair_recreates_missing_parent_directory(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.parent.rmdir()
        self.assertEqual(len(self.manager.repair_identical_copies("alpha")), 1)
        self.assertTrue(target.is_symlink())

    def test_repair_removes_created_directory_on_failure(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.parent.rmdir()
        with patch.object(linker.os, "symlink", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.manager.repair_identical_copies("alpha")
        self.assertFalse(target.parent.exists())

    def test_repair_blocks_missing_source(self):
        src = self.mod("alpha")
        extra = self.mod_extra("alpha", "archive/pc/mod/second.archive")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        other = self.game / extra.relative_to(self.mods / "alpha")
        other.unlink()
        extra.unlink()
        with self.assertRaises(FileNotFoundError):
            self.manager.repair_identical_copies("alpha")
        self.assertFalse(target.is_symlink())

    def test_repair_mixed_rollback(self):
        src = self.mod("alpha")
        extra = self.mod_extra("alpha", "archive/pc/mod/second.archive")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        other = self.game / extra.relative_to(self.mods / "alpha")
        other.unlink()
        original = linker.os.symlink
        count = [0]
        def fail_second(source, destination):
            count[0] += 1
            if count[0] == 2:
                raise OSError("simulated link failure")
            return original(source, destination)
        with patch.object(linker.os, "symlink", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.manager.repair_identical_copies("alpha")
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_bytes(), src.read_bytes())
        self.assertFalse(other.exists())

    def test_health_snapshot_disabled_and_healthy(self):
        self.mod("alpha")
        self.assertEqual(self.manager.health_snapshot()["alpha"]["level"], "disabled")
        self.manager.enable_mod("alpha")
        self.assertEqual(self.manager.health_snapshot()["alpha"],
                         {"level": "healthy", "issues": []})

    def test_health_snapshot_repairable_missing_and_identical_copy(self):
        src = self.mod("alpha")
        extra = self.mod_extra("alpha", "archive/pc/mod/extra.archive")
        self.manager.enable_mod("alpha")
        first = self.game / src.relative_to(self.mods / "alpha")
        second = self.game / extra.relative_to(self.mods / "alpha")
        first.unlink()
        first.write_bytes(src.read_bytes())
        second.unlink()
        health = self.manager.health_snapshot()["alpha"]
        self.assertEqual(health["level"], "repairable")
        self.assertEqual({status for _, status in health["issues"]},
                         {"identical_copy", "missing"})

    def test_health_snapshot_modified_file_blocks_repair(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_text("changed by game")
        health = self.manager.health_snapshot()["alpha"]
        self.assertEqual(health["level"], "blocked")
        self.assertEqual(health["issues"][0][1], "modified_file")

    def test_health_snapshot_detects_foreign_link(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        foreign = self.root / "other"
        foreign.write_text("foreign")
        target.symlink_to(foreign)
        self.assertEqual(self.manager.health_snapshot()["alpha"]["level"], "blocked")
        self.assertEqual(self.manager.inspect_reconcile("alpha")[0][1], "foreign_link")

    def test_health_snapshot_detects_missing_source(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        src.unlink()
        self.assertEqual(self.manager.inspect_reconcile("alpha")[0][1], "missing_source")
        self.assertEqual(self.manager.health_snapshot()["alpha"]["level"], "blocked")
        with self.assertRaises(FileExistsError):
            self.manager.repair_identical_copies("alpha")

    def test_health_snapshot_detects_replaced_source_symlink(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        src.unlink()
        replacement = self.root / "replacement"
        replacement.write_text("new")
        src.symlink_to(replacement)
        self.assertEqual(self.manager.inspect_reconcile("alpha")[0][1], "missing_source")
        self.assertEqual(self.manager.health_snapshot()["alpha"]["level"], "blocked")

    def test_health_backup_conflict_blocks_repair_offer(self):
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        target.write_bytes(src.read_bytes())
        backup = target.with_suffix(target.suffix + ".vanilla_bak")
        backup.write_text("original")
        health = self.manager.health_snapshot()["alpha"]
        self.assertEqual(health["level"], "blocked")
        self.assertEqual(health["issues"][0][1], "backup_conflict")
        with self.assertRaises(FileExistsError):
            self.manager.repair_identical_copies("alpha")
        self.assertEqual(target.read_bytes(), src.read_bytes())
        self.assertEqual(backup.read_text(), "original")

    def test_health_snapshot_isolates_inspection_errors(self):
        self.mod("alpha")
        self.mod("beta", "archive/pc/mod/beta.archive")
        self.manager.enable_mod("alpha")
        self.manager.enable_mod("beta")
        old = self.manager.inspect_reconcile

        def broken(name):
            if name == "alpha":
                raise OSError("read error")
            return old(name)

        with patch.object(self.manager, "inspect_reconcile", side_effect=broken):
            snapshot = self.manager.health_snapshot()
        self.assertEqual(snapshot["alpha"]["level"], "error")
        self.assertEqual(snapshot["beta"]["level"], "healthy")

    def test_legacy_verifier_flags_foreign_link(self):
        from core import analyzer
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        target = self.game / src.relative_to(self.mods / "alpha")
        target.unlink()
        foreign = self.root / "foreign"
        foreign.write_text("foreign")
        target.symlink_to(foreign)
        with patch.object(analyzer, "MODS_DIR", self.mods):
            issues = analyzer.verify_symlinks(self.state.state["mods"], self.game)
        self.assertEqual([i.issue for i in issues], ["foreign_link"])

    def test_legacy_verifier_flags_missing_original(self):
        from core import analyzer
        src = self.mod("alpha")
        self.manager.enable_mod("alpha")
        src.unlink()
        with patch.object(analyzer, "MODS_DIR", self.mods):
            issues = analyzer.verify_symlinks(self.state.state["mods"], self.game)
        self.assertEqual([i.issue for i in issues], ["missing_source"])

    def test_reject_path_traversal_name(self):
        for bad in ("../escape", "/absolute", "a/b", ".."):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                self.manager._validate_name(bad)

    def test_symlink_inside_mod_rejected(self):
        src = self.mod("alpha")
        (src.parent / "link.archive").symlink_to(src)
        with self.assertRaises(ValueError):
            self.manager.enable_mod("alpha")

    def test_rollback_on_link_failure(self):
        import os
        self.mod("alpha", "archive/pc/mod/one.archive")
        self.mod_extra("alpha", "archive/pc/mod/two.archive")
        original = linker.os.symlink
        calls = [0]

        def flaky(source, target):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("simulated failure")
            return original(source, target)

        with patch.object(linker.os, "symlink", side_effect=flaky):
            with self.assertRaises(OSError):
                self.manager.enable_mod("alpha")
        self.assertFalse(any(self.game.rglob("*.archive")))
        self.assertFalse(self.state.state["mods"]["alpha"]["enabled"])

    def mod_extra(self, name, relative):
        path = self.mods / name / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("second")
        return path


if __name__ == "__main__":
    unittest.main()
