import os
import filecmp
import uuid
import shutil
import tempfile
from pathlib import Path

from core.config import MODS_DIR, TEMP_DIR, StateManager
from core.normalizer import extract_archive, normalize_mod_structure


class ModManager:
    def __init__(self):
        self.state_mgr = StateManager()

    @staticmethod
    def _validate_name(name: str) -> str:
        if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Invalid mod name: use a single directory name.")
        return name

    @staticmethod
    def _files(mod_dir: Path):
        # Never deploy links embedded in untrusted archives.
        for path in mod_dir.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Symlinks inside mods are not supported: {path}")
            if path.is_file():
                yield path

    @staticmethod
    def _target(game_dir: Path, rel: Path) -> Path:
        root = game_dir.resolve()
        target = root / rel
        # Parents must not redirect an operation outside the game directory.
        if not target.parent.resolve().is_relative_to(root):
            raise ValueError(f"Target escapes game directory: {rel}")
        return target

    def install_from_archive(self, archive_path: str, custom_name: str = None):
        arch = Path(archive_path).expanduser().resolve()
        if not arch.is_file():
            raise FileNotFoundError(f"Archive not found: {arch}")
        name = self._validate_name(custom_name or arch.stem)
        mods = self.state_mgr.state["mods"]
        final_dir = MODS_DIR / name
        if name in mods or final_dir.exists():
            raise FileExistsError(f"Mod already installed: {name}")

        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="install-", dir=TEMP_DIR) as temp:
            workspace = Path(temp)
            raw_dir = workspace / "extracted"
            prepared_dir = workspace / "normalized"
            extract_archive(arch, raw_dir)
            normalize_mod_structure(raw_dir, prepared_dir)
            files = list(self._files(prepared_dir))
            if not files:
                raise ValueError("No supported mod files found in archive.")
            # Reject accidental traversal and conflicting files before publishing the mod.
            self._preflight(name, [(f.relative_to(prepared_dir), f) for f in files])
            prepared_dir.rename(final_dir)

        mods[name] = {"enabled": False, "links": []}
        self.state_mgr.save()
        try:
            self.enable_mod(name)
        except Exception:
            mods.pop(name, None)
            self.state_mgr.save()
            shutil.rmtree(final_dir)
            raise

    def _preflight(self, name: str, entries):
        game_dir = self.state_mgr.game_path
        if not game_dir.is_dir():
            raise FileNotFoundError(f"Game directory not found: {game_dir}")

        mods = self.state_mgr.state["mods"]
        occupied = {
            path: other_name
            for other_name, data in mods.items()
            if other_name != name and data.get("enabled")
            for path in data.get("links", [])
        }
        for rel, source in entries:
            target = self._target(game_dir, rel)
            owner = occupied.get(str(rel))
            if owner:
                raise FileExistsError(f"File conflict with mod '{owner}': {rel}")
            if target.is_symlink():
                raise FileExistsError(f"Existing symlink at {rel}")
            backup = target.with_suffix(target.suffix + ".vanilla_bak")
            if target.exists() and backup.exists() and not target.is_symlink():
                raise FileExistsError(f"Existing backup prevents safe deployment: {backup}")
            if backup.is_symlink():
                raise FileExistsError(f"Unsafe backup symlink: {backup}")

    def enable_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods:
            raise KeyError(f"Mod not found: {mod_name}")
        if mods[mod_name]["enabled"]:
            return

        mod_dir = MODS_DIR / mod_name
        entries = [(p.relative_to(mod_dir), p) for p in self._files(mod_dir)]
        self._preflight(mod_name, entries)
        game_dir = self.state_mgr.game_path
        completed = []
        try:
            for rel, source in entries:
                target = self._target(game_dir, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = target.with_suffix(target.suffix + ".vanilla_bak")
                had_original = target.exists() and not target.is_symlink()
                if had_original:
                    target.rename(backup)
                try:
                    os.symlink(source, target)
                except Exception:
                    if had_original:
                        backup.rename(target)
                    raise
                completed.append((target, source, backup if had_original else None))
        except Exception:
            for target, source, backup in reversed(completed):
                if target.is_symlink() and target.resolve() == source.resolve():
                    target.unlink()
                if backup is not None and backup.exists():
                    backup.rename(target)
            raise

        mods[mod_name]["enabled"] = True
        mods[mod_name]["links"] = [str(rel) for rel, _ in entries]
        self.state_mgr.save()

    def disable_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods or not mods[mod_name]["enabled"]:
            return
        game_dir = self.state_mgr.game_path
        mod_dir = MODS_DIR / mod_name

        # Validate everything before removing anything.
        targets = []
        for rel_str in mods[mod_name]["links"]:
            rel = Path(rel_str)
            target = self._target(game_dir, rel)
            source = mod_dir / rel
            if target.is_symlink() and target.resolve() != source.resolve():
                raise FileExistsError(f"Link is now owned by another mod: {rel}")
            if target.exists() and not target.is_symlink():
                raise FileExistsError(f"Target has been replaced by a regular file: {rel}")
            targets.append((target, source))

        for target, source in targets:
            if target.is_symlink() and target.resolve() == source.resolve():
                target.unlink()
                backup = target.with_suffix(target.suffix + ".vanilla_bak")
                if backup.exists():
                    backup.rename(target)
        mods[mod_name]["enabled"] = False
        mods[mod_name]["links"] = []
        self.state_mgr.save()


    def inspect_reconcile(self, mod_name: str):
        """Read-only check of tracked deployed files."""
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods:
            raise KeyError(f"Mod not found: {mod_name}")
        if not mods[mod_name]["enabled"]:
            raise ValueError(f"Mod is not enabled: {mod_name}")
        root = MODS_DIR / mod_name
        report = []
        for rel_str in mods[mod_name]["links"]:
            rel = Path(rel_str)
            source = root / rel
            target = self._target(self.state_mgr.game_path, rel)
            if target.is_symlink():
                status = "ok" if target.resolve() == source.resolve() else "foreign_link"
            elif target.is_file():
                status = ("identical_copy" if source.is_file()
                          and not source.is_symlink()
                          and filecmp.cmp(source, target, shallow=False)
                          else "modified_file")
            elif target.exists():
                status = "unexpected_target"
            else:
                status = "missing"
            if status != "ok":
                report.append((rel_str, status))
        return report

    def repair_identical_copies(self, mod_name: str):
        """Explicitly re-link byte-identical copies, leaving other files untouched."""
        report = self.inspect_reconcile(mod_name)
        blockers = [(rel, status) for rel, status in report if status != "identical_copy"]
        if blockers:
            raise FileExistsError(f"Repair blocked by unresolved targets: {blockers}")
        root = MODS_DIR / mod_name
        repaired = []
        for rel_str, _ in report:
            rel = Path(rel_str)
            source = root / rel
            target = self._target(self.state_mgr.game_path, rel)
            if (target.is_symlink() or not target.is_file()
                    or source.is_symlink() or not source.is_file()
                    or not filecmp.cmp(source, target, shallow=False)):
                raise FileExistsError(f"Target changed during repair: {rel}")
            temporary = target.with_name(target.name + ".reconcile-" + uuid.uuid4().hex)
            target.rename(temporary)
            try:
                os.symlink(source, target)
            except Exception:
                temporary.rename(target)
                raise
            temporary.unlink()
            repaired.append(str(rel))
        return repaired

    def remove_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods:
            raise KeyError(f"Mod not found: {mod_name}")
        if mods[mod_name]["enabled"]:
            self.disable_mod(mod_name)
        shutil.rmtree(MODS_DIR / mod_name)
        del mods[mod_name]
        self.state_mgr.save()
