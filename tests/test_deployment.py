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

    def test_repair_refuses_when_other_target_missing(self):
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
