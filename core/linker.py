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
        """Read-only audit of this enabled mod's tracked deployment."""
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
            source_valid = source.is_file() and not source.is_symlink()
            if target.is_symlink():
                if target.resolve() != source.resolve():
                    status = "foreign_link"
                elif not source_valid:
                    status = "missing_source"
                else:
                    status = "ok"
            elif not source_valid:
                status = "missing_source"
            elif target.is_file():
                status = ("identical_copy" if filecmp.cmp(source, target, shallow=False)
                          else "modified_file")
            elif target.exists():
                status = "unexpected_target"
            else:
                status = "missing"
            if status != "ok":
                report.append((rel_str, status))
        return report

    def health_snapshot(self):
        """Summarise all mods without modifying files or deployment state.

        Levels: disabled, healthy, repairable, blocked, error.
        A mod is repairable only when *every* issue can be safely reconciled.
        """
        results = {}
        for name, data in self.state_mgr.state["mods"].items():
            if not data.get("enabled"):
                results[name] = {"level": "disabled", "issues": []}
                continue
            try:
                issues = self.inspect_reconcile(name)
            except (OSError, ValueError, RuntimeError, KeyError) as exc:
                results[name] = {
                    "level": "error", "issues": [],
                    "error": str(exc),
                }
                continue
            if not issues:
                level = "healthy"
            elif all(status in ("identical_copy", "missing") for _, status in issues):
                level = "repairable"
            else:
                level = "blocked"
            results[name] = {"level": level, "issues": issues}
        return results

    def repair_identical_copies(self, mod_name: str):
        """Repair identical copies and absent targets, without touching altered files.

        Validate all targets first. Roll back completed changes on an ordinary
        error; copies are staged in the same directory until commit.
        """
        report = self.inspect_reconcile(mod_name)
        allowed = {"identical_copy", "missing"}
        blockers = [(rel, status) for rel, status in report if status not in allowed]
        if blockers:
            raise FileExistsError(f"Repair blocked by unresolved targets: {blockers}")

        game_dir = self.state_mgr.game_path
        root = MODS_DIR / mod_name
        steps = []
        for rel_str, status in report:
            rel = Path(rel_str)
            source = root / rel
            target = self._target(game_dir, rel)
            backup = target.with_suffix(target.suffix + ".vanilla_bak")
            if source.is_symlink() or not source.is_file():
                raise FileNotFoundError(f"Mod source is absent or unsafe: {rel}")
            if backup.exists() or backup.is_symlink():
                raise FileExistsError(f"Backup requires manual review: {backup}")
            if status == "identical_copy":
                if (target.is_symlink() or not target.is_file()
                        or not filecmp.cmp(source, target, shallow=False)):
                    raise FileExistsError(f"Target changed during repair: {rel}")
            elif target.exists() or target.is_symlink():
                raise FileExistsError(f"Missing target appeared during repair: {rel}")
            steps.append((rel, status, source, target))

        completed = []
        created_dirs = []
        try:
            for rel, status, source, ignored_target in steps:
                target = self._target(game_dir, rel)
                if status == "identical_copy":
                    if (target.is_symlink() or not target.is_file()
                            or not filecmp.cmp(source, target, shallow=False)):
                        raise FileExistsError(f"Target changed during repair: {rel}")
                    temporary = target.with_name(target.name + ".reconcile-" + uuid.uuid4().hex)
                    target.rename(temporary)
                else:
                    if target.exists() or target.is_symlink():
                        raise FileExistsError(f"Target appeared during repair: {rel}")
                    missing_parents = []
                    parent = target.parent
                    while not parent.exists() and not parent.is_symlink():
                        missing_parents.append(parent)
                        parent = parent.parent
                    for directory in reversed(missing_parents):
                        directory.mkdir()
                        created_dirs.append(directory)
                    target = self._target(game_dir, rel)
                    if target.exists() or target.is_symlink():
                        raise FileExistsError(f"Target appeared during repair: {rel}")
                    temporary = None
                try:
                    os.symlink(source, target)
                except Exception:
                    if temporary is not None:
                        temporary.rename(target)
                    raise
                completed.append((target, source, temporary))
        except Exception:
            for target, source, temporary in reversed(completed):
                if target.is_symlink() and target.resolve() == source.resolve():
                    target.unlink()
                if temporary is not None and temporary.exists():
                    temporary.rename(target)
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

        for target, source, temporary in completed:
            if temporary is not None:
                temporary.unlink()
        return [str(rel) for rel, _, _, _ in steps]

    def remove_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods:
            raise KeyError(f"Mod not found: {mod_name}")
        if mods[mod_name]["enabled"]:
            self.disable_mod(mod_name)
        shutil.rmtree(MODS_DIR / mod_name)
        del mods[mod_name]
        self.state_mgr.save()
