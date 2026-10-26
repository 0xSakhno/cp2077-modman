import os
import shutil
from pathlib import Path
from core.config import MODS_DIR, TEMP_DIR, StateManager
from core.normalizer import extract_archive, normalize_mod_structure


class ModManager:
    def __init__(self):
        self.state_mgr = StateManager()

    def install_from_archive(self, archive_path: str, custom_name: str = None):
        arch = Path(archive_path).resolve()
        if not arch.exists():
            raise FileNotFoundError(f"Архів не знайдено: {arch}")

        mod_name = custom_name or arch.stem
        raw_extract_dir = TEMP_DIR / mod_name
        final_mod_dir = MODS_DIR / mod_name

        print(f"[*] Розпакування '{arch.name}'...")
        extract_archive(arch, raw_extract_dir)

        print(f"[*] Нормалізація структури для '{mod_name}'...")
        normalize_mod_structure(raw_extract_dir, final_mod_dir)
        shutil.rmtree(raw_extract_dir, ignore_errors=True)

        # Перевірка, чи мод не порожній після нормалізації
        if not any(final_mod_dir.rglob("*")):
            shutil.rmtree(final_mod_dir, ignore_errors=True)
            raise ValueError("Не вдалося розпізнати структуру мода у цьому архіві.")

        self.state_mgr.state["mods"][mod_name] = {"enabled": False, "links": []}
        self.state_mgr.save()
        print(f"[+] Мод '{mod_name}' успішно додано в базу. Увімкнення...")
        self.enable_mod(mod_name)

    def enable_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods:
            raise KeyError(f"Мод '{mod_name}' не знайдено.")
        if mods[mod_name]["enabled"]:
            print(f"[!] Мод '{mod_name}' вже увімкнений.")
            return

        game_dir = self.state_mgr.game_path
        if not game_dir.exists():
            raise FileNotFoundError(f"Папка гри не існує: {game_dir}. Вкажіть правильний шлях.")

        mod_dir = MODS_DIR / mod_name
        created_links = []

        for src_file in mod_dir.rglob("*"):
            if src_file.is_file():
                rel_path = src_file.relative_to(mod_dir)
                target_file = game_dir / rel_path

                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Якщо там вже є старий симлінк (конфлікт з іншим модом) — перезаписуємо
                if target_file.is_symlink():
                    target_file.unlink()
                elif target_file.exists():
                    # Якщо це оригінальний файл гри — робимо бекап
                    backup = target_file.with_suffix(target_file.suffix + ".vanilla_bak")
                    if not backup.exists():
                        target_file.rename(backup)

                os.symlink(src_file, target_file)
                created_links.append(str(rel_path))

        mods[mod_name]["enabled"] = True
        mods[mod_name]["links"] = created_links
        self.state_mgr.save()
        print(f"[+] Мод '{mod_name}' увімкнено ({len(created_links)} файлів злінковано).")

    def disable_mod(self, mod_name: str):
        mods = self.state_mgr.state["mods"]
        if mod_name not in mods or not mods[mod_name]["enabled"]:
            print(f"[!] Мод '{mod_name}' не активний.")
            return

        game_dir = self.state_mgr.game_path
        for rel_str in mods[mod_name]["links"]:
            target_file = game_dir / rel_str
            if target_file.is_symlink():
                target_file.unlink()

                # Відновлюємо бекап оригінального файлу, якщо він був
                backup = target_file.with_suffix(target_file.suffix + ".vanilla_bak")
                if backup.exists():
                    backup.rename(target_file)

                # Підчищаємо порожні папки в грі вгору по дереву
                parent = target_file.parent
                while parent != game_dir and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent

        mods[mod_name]["enabled"] = False
        mods[mod_name]["links"] = []
        self.state_mgr.save()
        print(f"[-] Мод '{mod_name}' вимкнено, симлінки видалено.")

    def remove_mod(self, mod_name: str):
        if mod_name not in self.state_mgr.state["mods"]:
            raise KeyError(f"Мод '{mod_name}' не знайдено.")

        if self.state_mgr.state["mods"][mod_name]["enabled"]:
            self.disable_mod(mod_name)

        shutil.rmtree(MODS_DIR / mod_name, ignore_errors=True)
        del self.state_mgr.state["mods"][mod_name]
        self.state_mgr.save()
        print(f"[x] Мод '{mod_name}' повністю видалено з диска.")