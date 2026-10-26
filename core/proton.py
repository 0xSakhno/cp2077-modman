"""
Модуль інтеграції з Proton (Wine) та Steam для Cyberpunk 2077 на Linux.

Забезпечує:
1. Автоматичне налаштування DLL Overrides (version.dll для CET, winmm.dll для RED4ext)
   у префіксі Proton (user.reg), без яких моди під Linux/Steam Deck не працюють взагалі.
2. Запуск гри зі скіпом REDprelauncher та активацією модового режиму (--launcher-skip -modded).
3. Готовий рядок параметрів для налаштувань запуску в самому клієнті Steam.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from core.config import CP2077_APP_ID

RECOMMENDED_STEAM_OPTIONS = 'WINEDLLOVERRIDES="version=n,b;winmm=n,b" %command% --launcher-skip -modded'


def find_proton_prefix(game_path: Path | None = None) -> Path | None:
    """Знаходить папку wine-префіксу Proton для Cyberpunk 2077 (compatdata/1091500/pfx)."""
    candidates = []

    if game_path and game_path.exists():
        # Зазвичай compatdata лежить поруч із common у тій самій бібліотеці Steam
        try:
            candidates.append(game_path.parents[1] / "compatdata" / CP2077_APP_ID / "pfx")
        except IndexError:
            pass

    home = Path.home()
    candidates.extend([
        home / ".local/share/Steam/steamapps/compatdata" / CP2077_APP_ID / "pfx",
        home / ".steam/steam/steamapps/compatdata" / CP2077_APP_ID / "pfx",
        home / ".steam/root/steamapps/compatdata" / CP2077_APP_ID / "pfx",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata" / CP2077_APP_ID / "pfx",
    ])

    for c in candidates:
        if (c / "user.reg").exists():
            return c.resolve()

    return None


def check_proton_overrides(prefix_path: Path) -> tuple[bool, list[str]]:
    """
    Перевіряє, чи активні необхідні DLL Overrides (version, winmm) у user.reg префіксу.
    Повертає (all_ok, missing_list).
    """
    user_reg = prefix_path / "user.reg"
    if not user_reg.exists():
        return False, ["version", "winmm"]

    try:
        text = user_reg.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False, ["version", "winmm"]

    # Шукаємо секцію [Software\\Wine\\DllOverrides]
    match = re.search(r"\[Software\\\\Wine\\\\DllOverrides\][\s\S]*?(?=\n\[|\Z)", text)
    if not match:
        return False, ["version", "winmm"]

    section = match.group(0)
    missing = []
    for dll in ["version", "winmm"]:
        # Перевіряємо наявність запису на зразок "version"="native,builtin" або "version"="native"
        if not re.search(rf'"{dll}"\s*=\s*"[^"]*native[^"]*"', section, re.IGNORECASE):
            missing.append(dll)

    return (len(missing) == 0), missing


def configure_proton_overrides(prefix_path: Path, dlls: list[str] = ("version", "winmm")) -> tuple[bool, str]:
    """
    Автоматично прописує DLL Overrides у user.reg префіксу Proton.
    Створює бекап user.reg.bak перед внесенням змін.
    """
    user_reg = prefix_path / "user.reg"
    if not user_reg.exists():
        return False, f"File not found: {user_reg}."

    try:
        text = user_reg.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return False, f"Could not read user.reg: {e}"

    # Створюємо резервну копію, якщо ще не створена
    bak = user_reg.with_suffix(".reg.bak")
    if not bak.exists():
        try:
            shutil.copy2(user_reg, bak)
        except Exception as e:
            return False, f"Could not back up user.reg: {e}"

    # Знаходимо або створюємо секцію [Software\\Wine\\DllOverrides]
    header_match = re.search(r"(\[Software\\\\Wine\\\\DllOverrides\][^\n]*\n(?:#[^\n]*\n)?)", text)

    lines_to_add = []
    for dll in dlls:
        # Якщо вже є правильний запис — пропускаємо
        if not re.search(rf'"{dll}"\s*=\s*"[^"]*native[^"]*"', text, re.IGNORECASE):
            lines_to_add.append(f'"{dll}"="native,builtin"\n')

    if not lines_to_add:
        return True, "All required DLL overrides are already enabled."

    insert_content = "".join(lines_to_add)

    if header_match:
        # Вставляємо одразу під заголовок секції
        pos = header_match.end()
        new_text = text[:pos] + insert_content + text[pos:]
    else:
        # Додаємо нову секцію в кінець
        new_text = text.rstrip() + "\n\n[Software\\\\Wine\\\\DllOverrides]\n" + insert_content

    try:
        user_reg.write_text(new_text, encoding="utf-8")
        return True, f"Successfully added DLL overrides ({', '.join(dlls)}) to the Proton prefix."
    except Exception as e:
        return False, f"Could not write to user.reg: {e}"


def launch_game_steam(game_path: Path | None = None) -> tuple[bool, str]:
    """
    Запускає Cyberpunk 2077 через Steam з прапорцями --launcher-skip та -modded.
    Перед запуском перевіряє та за необхідності автоматично виправляє DLL Overrides у Proton.
    """
    # 1. Автоперевірка та налаштування Proton prefix
    pfx = find_proton_prefix(game_path)
    if pfx:
        ok, missing = check_proton_overrides(pfx)
        if not ok:
            configure_proton_overrides(pfx, missing)

    # 2. Спроба запуску через команду steam CLI (найнадійніший спосіб з передачею аргументів)
    try:
        subprocess.Popen(["steam", "-applaunch", CP2077_APP_ID, "--launcher-skip", "-modded"])
        return True, "Game launched through Steam (-applaunch 1091500 --launcher-skip -modded)"
    except FileNotFoundError:
        pass

    # 3. Fallback через xdg-open URL схему
    try:
        subprocess.Popen(["xdg-open", f"steam://run/{CP2077_APP_ID}//--launcher-skip%20-modded/"])
        return True, "Game launched through Steam URL (steam://run/...)"
    except Exception as e:
        return False, f"Could not launch game: {e}"
