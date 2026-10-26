import json
import re
from pathlib import Path

APP_DIR = Path.home() / ".local" / "share" / "cp2077-modman"
MODS_DIR = APP_DIR / "mods"
TEMP_DIR = APP_DIR / "tmp"
STATE_FILE = APP_DIR / "state.json"

CP2077_APP_ID = "1091500"


def auto_find_cyberpunk() -> Path:
    """Автоматично шукає Cyberpunk 2077 у бібліотеках Steam на всіх дисках та в Heroic/Lutris."""
    home = Path.home()

    # 1. Пошук через конфіг бібліотек Steam (libraryfolders.vdf)
    vdf_candidates = [
        home / ".local/share/Steam/steamapps/libraryfolders.vdf",
        home / ".steam/steam/steamapps/libraryfolders.vdf",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/libraryfolders.vdf",
    ]

    steam_libraries = []
    for vdf in vdf_candidates:
        if vdf.exists():
            content = vdf.read_text(encoding="utf-8", errors="ignore")
            # Витягуємо всі шляхи "path" "/шлях/до/SteamLibrary"
            paths = re.findall(r'"path"\s+"([^"]+)"', content)
            steam_libraries.extend(Path(p) for p in paths)
            break

    # Перевіряємо кожну знайдену бібліотеку Steam на наявність гри
    for lib in steam_libraries:
        cp_dir = lib / "steamapps/common/Cyberpunk 2077"
        if (cp_dir / "bin/x64/Cyberpunk2077.exe").exists():
            return cp_dir.resolve()

    # 2. Резервний пошук у стандартних папках (GOG / Heroic / Lutris / зовнішні диски)
    fallback_roots = [
        home / "Games",
        home / "Games/Heroic",
        Path("/mnt"),
        Path("/run/media") / home.name,
    ]

    for root in fallback_roots:
        if not root.exists():
            continue
        # Шукаємо не глибше 3 рівнів, щоб не вішати систему
        for exe in root.glob("*/*/bin/x64/Cyberpunk2077.exe"):
            return exe.parents[2].resolve()
        for exe in root.glob("*/bin/x64/Cyberpunk2077.exe"):
            return exe.parents[2].resolve()

    # Якщо нічого не знайдено — повертаємо дефолтний шлях
    return home / ".local/share/Steam/steamapps/common/Cyberpunk 2077"


class StateManager:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        MODS_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        if not STATE_FILE.exists():
            detected_path = auto_find_cyberpunk()
            initial_state = {
                "game_path": str(detected_path),
                "mods": {}
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(initial_state, f, indent=4, ensure_ascii=False)
            return initial_state

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Якщо збережений шлях раптом став невалідним — пробуємо знайти знову
        if not Path(data.get("game_path", "")).exists():
            data["game_path"] = str(auto_find_cyberpunk())
        return data

    def save(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=4, ensure_ascii=False)

    @property
    def game_path(self) -> Path:
        return Path(self.state["game_path"])

    @game_path.setter
    def game_path(self, path: str):
        self.state["game_path"] = str(Path(path).expanduser().resolve())
        self.save()