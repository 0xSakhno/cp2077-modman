"""Security regression tests for streaming extraction of untrusted archives."""

import io
import os
import stat
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import normalizer
import core.linker as linker


class ArchiveSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / "extracted"

    def _zip(self, entries, name="mod.zip"):
        archive = self.root / name
        with zipfile.ZipFile(archive, "w") as z:
            for pathname, contents in entries:
                z.writestr(pathname, contents)
        return archive

    def _tar(self, entries, name="mod.tar"):
        archive = self.root / name
        with tarfile.open(archive, "w") as t:
            for entry in entries:
                data = entry.pop("data", None)
                info = tarfile.TarInfo(entry["name"])
                info.type = entry.get("type", tarfile.REGTYPE)
                info.linkname = entry.get("linkname", "")
                if data is not None:
                    payload = data.encode()
                    info.size = len(payload)
                    t.addfile(info, io.BytesIO(payload))
                else:
                    t.addfile(info)
        return archive

    def test_extract_valid_zip_with_unicode_and_nested_files(self):
        archive = self._zip([
            ("./r6/scripts/Мод/", ""),
            ("./r6/scripts/Мод/main.reds", "test content"),
            ("archive/pc/mod/plugin.archive", "binary"),
        ])
        normalizer.extract_archive(archive, self.dest)
        self.assertEqual((self.dest / "r6/scripts/Мод/main.reds").read_text(), "test content")
        self.assertEqual((self.dest / "archive/pc/mod/plugin.archive").read_text(), "binary")

    def test_extract_valid_tar(self):
        archive = self._tar([
            {"name": "r6/scripts/foo.reds", "data": "script"},
            {"name": "archive/pc/mod/bar.archive", "data": "stuff"},
        ])
        normalizer.extract_archive(archive, self.dest)
        self.assertEqual((self.dest / "r6/scripts/foo.reds").read_text(), "script")

    def test_reject_absolute_zip_path_and_discard_partial_extraction(self):
        archive = self._zip([
            ("r6/scripts/good.reds", "ok"),
            ("/tmp/cp2077-unsafe-absolute-path.txt", "bad"),
        ])
        with self.assertRaises(ValueError):
            normalizer.extract_archive(archive, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_parent_traversal(self):
        escaped = self.root / "escaped.reds"
        archive = self._zip([
            ("r6/scripts/good.reds", "safe"),
            ("../escaped.reds", "malicious"),
        ])
        with self.assertRaisesRegex(ValueError, "escapes"):
            normalizer.extract_archive(archive, self.dest)
        self.assertFalse(escaped.exists())
        self.assertFalse(self.dest.exists())

    def test_reject_windows_and_backslash_paths(self):
        for bad in ("C:/Windows/exploit.reds", "r6\\..\\outside.reds"):
            with self.subTest(path=bad):
                archive = self._zip([(bad, "bad")])
                with self.assertRaises(ValueError):
                    normalizer.extract_archive(archive, self.dest)
                self.assertFalse(self.dest.exists())

    def test_reject_tar_symlink(self):
        archive = self._tar([
            {"name": "r6/scripts/bad.reds", "type": tarfile.SYMTYPE,
             "linkname": "../../outside"},
        ])
        with self.assertRaisesRegex(ValueError, "unsafe archive entry type|Unsupported or unsafe"):
            normalizer.extract_archive(archive, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_tar_hardlink(self):
        archive = self._tar([
            {"name": "r6/scripts/bad.reds", "type": tarfile.LNKTYPE,
             "linkname": "../../outside"},
        ])
        with self.assertRaisesRegex(ValueError, "unsafe archive entry type|Unsupported or unsafe"):
            normalizer.extract_archive(archive, self.dest)

    def test_reject_tar_special_file(self):
        archive = self._tar([
            {"name": "r6/scripts/device", "type": tarfile.CHRTYPE},
        ])
        with self.assertRaisesRegex(ValueError, "unsafe archive entry type|Unsupported or unsafe"):
            normalizer.extract_archive(archive, self.dest)

    def test_reject_zip_unix_symlink(self):
        archive = self.root / "link.zip"
        symlink = zipfile.ZipInfo("r6/scripts/link.reds")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(symlink, "../../outside")
        with self.assertRaisesRegex(ValueError, "unsafe archive entry type|Unsupported or unsafe"):
            normalizer.extract_archive(archive, self.dest)

    def test_reject_duplicate_paths(self):
        archive = self.root / "duplicates.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("r6/scripts/duplicated.reds", "first")
                z.writestr("r6/scripts/duplicated.reds", "second")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalizer.extract_archive(archive, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_too_many_archive_entries(self):
        archive = self._zip([
            ("r6/scripts/one.reds", "1"),
            ("r6/scripts/two.reds", "2"),
        ])
        with patch.object(normalizer, "MAX_ARCHIVE_ENTRIES", 1):
            with self.assertRaisesRegex(ValueError, "number of entries"):
                normalizer.extract_archive(archive, self.dest)

    def test_reject_excessive_decompressed_size(self):
        archive = self._zip([("r6/scripts/too-big.reds", "123456")])
        with patch.object(normalizer, "MAX_SINGLE_FILE_BYTES", 4):
            with self.assertRaisesRegex(ValueError, "per-file size limit"):
                normalizer.extract_archive(archive, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_total_size_limit(self):
        archive = self._zip([
            ("r6/scripts/a.reds", "123"),
            ("r6/scripts/b.reds", "456"),
        ])
        with patch.object(normalizer, "MAX_TOTAL_EXTRACTED_BYTES", 5):
            with self.assertRaisesRegex(ValueError, "size limit"):
                normalizer.extract_archive(archive, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_control_characters_in_paths(self):
        archive = self._zip([("r6/scripts/bad\nname.reds", "bad")])
        with self.assertRaisesRegex(ValueError, "control characters"):
            normalizer.extract_archive(archive, self.dest)

    def test_valid_archive_installs_and_disables_end_to_end(self):
        archive = self._zip([("r6/scripts/example.reds", "print('hello')")])
        game = self.root / "game"
        game.mkdir()
        mods = self.root / "mods"
        mods.mkdir()
        staging = self.root / "staging"
        staging.mkdir()

        class FakeState:
            game_path = game
            def __init__(self):
                self.state = {"mods": {}}
            def save(self):
                pass

        manager = linker.ModManager.__new__(linker.ModManager)
        manager.state_mgr = FakeState()
        with patch.object(linker, "MODS_DIR", mods), patch.object(linker, "TEMP_DIR", staging):
            manager.install_from_archive(str(archive), "example")
            target = game / "r6/scripts/example.reds"
            source = mods / "example/r6/scripts/example.reds"
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), source.resolve())
            self.assertEqual(source.read_text(), "print('hello')")
            self.assertTrue(manager.state_mgr.state["mods"]["example"]["enabled"])
            manager.disable_mod("example")
            self.assertFalse(target.is_symlink())
            self.assertFalse(target.exists())
            self.assertTrue(source.exists())

    def test_bad_archive_never_registers_or_deploys_mod(self):
        archive = self._zip([
            ("r6/scripts/good.reds", "safe"),
            ("../../outside.reds", "escape"),
        ])
        game = self.root / "game"
        game.mkdir()
        mods = self.root / "mods"
        mods.mkdir()
        staging = self.root / "staging"
        staging.mkdir()

        class FakeState:
            game_path = game
            def __init__(self):
                self.state = {"mods": {}}
            def save(self):
                pass

        manager = linker.ModManager.__new__(linker.ModManager)
        manager.state_mgr = FakeState()
        with patch.object(linker, "MODS_DIR", mods), patch.object(linker, "TEMP_DIR", staging):
            with self.assertRaises(ValueError):
                manager.install_from_archive(str(archive), "unsafe")
        self.assertEqual(manager.state_mgr.state["mods"], {})
        self.assertFalse((mods / "unsafe").exists())
        self.assertFalse((game / "r6/scripts/good.reds").exists())
        self.assertFalse((self.root / "outside.reds").exists())


if __name__ == "__main__":
    unittest.main()
