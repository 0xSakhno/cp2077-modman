"""
Модуль аналізу залежностей, конфліктів та верифікації модів.

Визначає:
- Які фреймворки потрібні для кожного мода (за структурою файлів)
- Чи встановлені ці фреймворки в папці гри
- Конфлікти між модами (два моди → один цільовий файл)
- Цілісність симлінків
- Версію гри (з PE-заголовку Cyberpunk2077.exe)
"""

import struct
from pathlib import Path
from dataclasses import dataclass, field

from core.config import MODS_DIR


# ══════════════════════════════════════════════════════════════════════
#  Framework definitions
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Framework:
    """Describes a known modding framework for Cyberpunk 2077."""
    id: str
    name: str
    # Files/dirs whose presence inside a MOD tells us it needs this framework
    mod_indicators: list[str]
    # Files whose presence inside the GAME directory tells us it's installed
    game_check_paths: list[str]
    url: str = ""


KNOWN_FRAMEWORKS: list[Framework] = [
    Framework(
        id="redscript",
        name="Redscript",
        mod_indicators=["r6/scripts/"],
        game_check_paths=[
            "engine/tools/scc.exe",
            "r6/scripts/redscript.toml",
        ],
        url="https://www.nexusmods.com/cyberpunk2077/mods/1511",
    ),
    Framework(
        id="cet",
        name="Cyber Engine Tweaks (CET)",
        mod_indicators=["bin/x64/plugins/cyber_engine_tweaks/"],
        game_check_paths=[
            "bin/x64/plugins/cyber_engine_tweaks.asi",
            "bin/x64/plugins/cyber_engine_tweaks/",
        ],
        url="https://www.nexusmods.com/cyberpunk2077/mods/107",
    ),
    Framework(
        id="red4ext",
        name="RED4ext",
        mod_indicators=["red4ext/plugins/"],
        game_check_paths=[
            "red4ext/RED4ext.dll",
        ],
        url="https://www.nexusmods.com/cyberpunk2077/mods/2380",
    ),
    Framework(
        id="archivexl",
        name="ArchiveXL",
        mod_indicators=[],  # Detected via .xl file extension below
        game_check_paths=[
            "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
            "red4ext/plugins/archive_xl/ArchiveXL.dll",
        ],
        url="https://www.nexusmods.com/cyberpunk2077/mods/4198",
    ),
    Framework(
        id="tweakxl",
        name="TweakXL",
        mod_indicators=[],  # Detected via .yaml in r6/tweaks/ below
        game_check_paths=[
            "red4ext/plugins/TweakXL/TweakXL.dll",
            "red4ext/plugins/tweak_xl/TweakXL.dll",
        ],
        url="https://www.nexusmods.com/cyberpunk2077/mods/4197",
    ),
]

# Map framework id → Framework for quick lookups
_FW_MAP: dict[str, Framework] = {fw.id: fw for fw in KNOWN_FRAMEWORKS}


# ══════════════════════════════════════════════════════════════════════
#  Dependency detection
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ModAnalysis:
    """Result of analysing a single mod's dependencies."""
    mod_name: str
    required_frameworks: list[str] = field(default_factory=list)   # framework ids
    missing_frameworks: list[str] = field(default_factory=list)    # framework ids not installed
    file_types: dict[str, int] = field(default_factory=dict)       # ext → count


def detect_mod_dependencies(mod_name: str) -> list[str]:
    """
    Analyse the mod's file structure and return a list of framework IDs it likely requires.
    """
    mod_dir = MODS_DIR / mod_name
    if not mod_dir.exists():
        return []

    required: set[str] = set()
    all_files = list(mod_dir.rglob("*"))

    for fw in KNOWN_FRAMEWORKS:
        for indicator in fw.mod_indicators:
            # indicator is a relative dir prefix like "r6/scripts/"
            indicator_path = mod_dir / indicator
            if indicator_path.exists() and indicator_path.is_dir():
                required.add(fw.id)
                break
            # Also check if any file's relative path starts with the indicator
            for f in all_files:
                if f.is_file():
                    try:
                        rel = str(f.relative_to(mod_dir))
                        if rel.replace("\\", "/").startswith(indicator.rstrip("/")):
                            required.add(fw.id)
                            break
                    except ValueError:
                        pass
                if fw.id in required:
                    break

    # Extension-based detection
    for f in all_files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        rel = str(f.relative_to(mod_dir)).replace("\\", "/").lower()

        if ext == ".xl":
            required.add("archivexl")
        if ext in (".yaml", ".yml") and "r6/tweaks" in rel:
            required.add("tweakxl")
        if ext == ".reds":
            required.add("redscript")
        if ext == ".lua" and "cyber_engine_tweaks" in rel:
            required.add("cet")

    # If ArchiveXL or TweakXL detected, they also need RED4ext
    if required & {"archivexl", "tweakxl"}:
        required.add("red4ext")

    return sorted(required)


def check_framework_installed(framework_id: str, game_path: Path) -> bool:
    """Check if a given framework is installed in the game directory."""
    fw = _FW_MAP.get(framework_id)
    if not fw:
        return True  # Unknown framework, assume OK

    for check_path in fw.game_check_paths:
        full = game_path / check_path
        if full.exists():
            return True
    return False


def analyse_mod(mod_name: str, game_path: Path) -> ModAnalysis:
    """Full analysis of a mod: dependencies + check which are missing."""
    required = detect_mod_dependencies(mod_name)
    missing = [
        fid for fid in required
        if not check_framework_installed(fid, game_path)
    ]

    # Count file types
    mod_dir = MODS_DIR / mod_name
    file_types: dict[str, int] = {}
    if mod_dir.exists():
        for f in mod_dir.rglob("*"):
            if f.is_file():
                ext = f.suffix.lower() or "(no ext)"
                file_types[ext] = file_types.get(ext, 0) + 1

    return ModAnalysis(
        mod_name=mod_name,
        required_frameworks=required,
        missing_frameworks=missing,
        file_types=file_types,
    )


# ══════════════════════════════════════════════════════════════════════
#  Conflict detection
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ModConflict:
    """Represents a conflict: two mods targeting the same file."""
    file_path: str           # relative path in the game directory
    mod_a: str
    mod_b: str


def detect_conflicts(mods_state: dict) -> list[ModConflict]:
    """
    Find all conflicts among ENABLED mods.
    A conflict = two enabled mods that both have a link to the same relative path.
    """
    # Build mapping: relative_path → list of mod names that use it
    path_owners: dict[str, list[str]] = {}

    for mod_name, data in mods_state.items():
        if not data.get("enabled"):
            continue
        for rel_path in data.get("links", []):
            normalised = rel_path.replace("\\", "/").lower()
            path_owners.setdefault(normalised, []).append(mod_name)

    conflicts: list[ModConflict] = []
    for rel_path, owners in path_owners.items():
        if len(owners) > 1:
            # Create pairwise conflicts
            for i in range(len(owners)):
                for j in range(i + 1, len(owners)):
                    conflicts.append(ModConflict(
                        file_path=rel_path,
                        mod_a=owners[i],
                        mod_b=owners[j],
                    ))
    return conflicts


def get_mod_conflicts_for(mod_name: str, mods_state: dict) -> list[ModConflict]:
    """Get conflicts for a specific mod only."""
    return [c for c in detect_conflicts(mods_state) if c.mod_a == mod_name or c.mod_b == mod_name]


# ══════════════════════════════════════════════════════════════════════
#  Symlink integrity verification
# ══════════════════════════════════════════════════════════════════════

@dataclass
class LinkIssue:
    """A single broken or invalid symlink."""
    mod_name: str
    rel_path: str
    issue: str  # "broken", "not_symlink", "missing"


def verify_symlinks(mods_state: dict, game_path: Path) -> list[LinkIssue]:
    """
    Verify that all symlinks of enabled mods are intact.
    Returns a list of issues found.
    """
    issues: list[LinkIssue] = []

    for mod_name, data in mods_state.items():
        if not data.get("enabled"):
            continue
        for rel_path in data.get("links", []):
            target = game_path / rel_path
            if not target.exists() and not target.is_symlink():
                issues.append(LinkIssue(mod_name, rel_path, "missing"))
            elif target.is_symlink():
                if not target.resolve().exists():
                    issues.append(LinkIssue(mod_name, rel_path, "broken"))
            else:
                # File exists but is not a symlink (game was updated and overwrote?)
                issues.append(LinkIssue(mod_name, rel_path, "not_symlink"))

    return issues


# ══════════════════════════════════════════════════════════════════════
#  Game version detection (from PE header)
# ══════════════════════════════════════════════════════════════════════

def get_game_version(game_path: Path) -> str | None:
    """
    Read the game version from Cyberpunk2077.exe's PE version resource.
    Returns a version string like "2.21.0.0" or None if parsing fails.
    """
    exe = game_path / "bin" / "x64" / "Cyberpunk2077.exe"
    if not exe.exists():
        return None
    try:
        return _parse_pe_version(exe)
    except Exception:
        return None


def _parse_pe_version(exe_path: Path) -> str | None:
    """
    Parse the game patch version from a PE executable.
    Prioritizes ProductVersion (e.g. '2.5') from StringFileInfo / VS_FIXEDFILEINFO,
    falling back to FileVersion if ProductVersion is not present.
    """
    try:
        data = exe_path.read_bytes()
    except Exception:
        return None

    # 1. Спробувати витягнути рядок ProductVersion з блоку StringFileInfo (UTF-16LE)
    pv_key = "ProductVersion".encode("utf-16le")
    pos = data.find(pv_key)
    if pos != -1:
        val_start = pos + len(pv_key)
        # Пропускаємо термінатор ключа та вирівнювання по 4-байтовій межі (нульові байти)
        while val_start < len(data) and data[val_start:val_start+2] == b"\x00\x00":
            val_start += 2
        val_end = val_start
        while val_end + 1 < len(data) and data[val_end:val_end+2] != b"\x00\x00":
            val_end += 2
        try:
            ver_str = data[val_start:val_end].decode("utf-16le").strip()
            if ver_str and any(c.isdigit() for c in ver_str) and len(ver_str) < 32:
                return ver_str
        except Exception:
            pass

    # 2. Якщо рядковий блок відсутній, читаємо ProductVersion з VS_FIXEDFILEINFO
    # VS_FIXEDFILEINFO signature: 0xFEEF04BD
    sig = b"\xbd\x04\xef\xfe"
    pos = data.find(sig)
    if pos != -1:
        try:
            # dwProductVersionMS (+16) та dwProductVersionLS (+20)
            p_ms = struct.unpack_from("<I", data, pos + 16)[0]
            p_ls = struct.unpack_from("<I", data, pos + 20)[0]
            if p_ms != 0 or p_ls != 0:
                major = (p_ms >> 16) & 0xFFFF
                minor = p_ms & 0xFFFF
                patch = (p_ls >> 16) & 0xFFFF
                build = p_ls & 0xFFFF
                if build > 0:
                    return f"{major}.{minor}.{patch}.{build}"
                if patch > 0:
                    return f"{major}.{minor}.{patch}"
                return f"{major}.{minor}"

            # 3. Fallback: dwFileVersionMS (+8) та dwFileVersionLS (+12)
            f_ms = struct.unpack_from("<I", data, pos + 8)[0]
            f_ls = struct.unpack_from("<I", data, pos + 12)[0]
            major = (f_ms >> 16) & 0xFFFF
            minor = f_ms & 0xFFFF
            patch = (f_ls >> 16) & 0xFFFF
            build = f_ls & 0xFFFF
            return f"{major}.{minor}.{patch}.{build}"
        except (struct.error, IndexError):
            pass

    return None


# ══════════════════════════════════════════════════════════════════════
#  Utility: get framework info for display
# ══════════════════════════════════════════════════════════════════════

def get_framework_info(framework_id: str) -> Framework | None:
    return _FW_MAP.get(framework_id)


def get_all_frameworks_status(game_path: Path) -> dict[str, bool]:
    """Return a dict of framework_id → is_installed for all known frameworks."""
    return {
        fw.id: check_framework_installed(fw.id, game_path)
        for fw in KNOWN_FRAMEWORKS
    }
