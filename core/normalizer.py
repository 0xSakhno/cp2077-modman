import shutil
import subprocess
from pathlib import Path

# Кореневі папки Cyberpunk 2077, за якими ми визначаємо структуру
KNOWN_ROOT_DIRS = {"archive", "bin", "r6", "red4ext", "mods", "engine"}

# Куди класти "голі" файли, якщо автор не створив папок
EXT_ROUTING = {
    ".archive": Path("archive/pc/mod"),
    ".xl": Path("archive/pc/mod"),
    ".reds": Path("r6/scripts"),
    ".yaml": Path("r6/tweaks"),
    ".yml": Path("r6/tweaks"),
}


def extract_archive(archive_path: Path, extract_to: Path):
    """Розпаковує будь-який архів (.zip, .7z, .rar) через системний bsdtar."""
    if extract_to.exists():
        shutil.rmtree(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)

    res = subprocess.run(
        ["bsdtar", "-xf", str(archive_path), "-C", str(extract_to)],
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        raise RuntimeError(f"Помилка розпакування {archive_path.name}: {res.stderr}")


def normalize_mod_structure(raw_dir: Path, target_mod_dir: Path):
    """
    Аналізує розпакований архів і будує чисту ієрархію відносно кореня гри.
    """
    if target_mod_dir.exists():
        shutil.rmtree(target_mod_dir)
    target_mod_dir.mkdir(parents=True, exist_ok=True)

    # 1. Шукаємо, чи є всередині вже готові кореневі папки (bin, r6, archive...)
    found_roots = []
    for path in raw_dir.rglob("*"):
        if path.is_dir() and path.name.lower() in KNOWN_ROOT_DIRS:
            # Перевіряємо, чи ця папка не є підпапкою вже знайденого кореня
            if not any(p in path.parents for p in found_roots):
                found_roots.append(path)

    if found_roots:
        # Якщо знайшли стандартні папки — переносимо їх відносно їхнього спільного батька
        for root_folder in found_roots:
            dest = target_mod_dir / root_folder.name.lower()
            shutil.copytree(root_folder, dest, dirs_exist_ok=True)
        return

    # 2. Якщо стандартних папок немає (автор закинув голі .archive або .yaml)
    for file_path in raw_dir.rglob("*"):
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext in EXT_ROUTING:
                rel_dir = EXT_ROUTING[ext]
                # Для .reds та .yaml бажано зберегти підпапку з назвою мода
                if ext in {".reds", ".yaml", ".yml"}:
                    dest_dir = target_mod_dir / rel_dir / target_mod_dir.name
                else:
                    dest_dir = target_mod_dir / rel_dir

                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_dir / file_path.name)