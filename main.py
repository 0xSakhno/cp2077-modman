#!/usr/bin/env python3
import argparse
from core.linker import ModManager


def main():
    parser = argparse.ArgumentParser(description="Cyberpunk 2077 Linux Mod Manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Команда встановлення шляху до гри
    p_path = sub.add_parser("set-path", help="Вказати шлях до папки Cyberpunk 2077")
    p_path.add_argument("path", help="Повний шлях до кореневої папки гри")

    # Встановлення архіву
    p_add = sub.add_parser("add", help="Встановити мод з архіву (.zip, .7z, .rar)")
    p_add.add_argument("archive", help="Шлях до архіву")
    p_add.add_argument("--name", help="Власна назва мода (опціонально)", default=None)

    # Увімкнення / Вимкнення / Видалення
    p_en = sub.add_parser("enable", help="Увімкнути мод")
    p_en.add_argument("name", help="Назва мода")

    p_dis = sub.add_parser("disable", help="Вимкнути мод")
    p_dis.add_argument("name", help="Назва мода")

    p_rm = sub.add_parser("remove", help="Повністю видалити мод")
    p_rm.add_argument("name", help="Назва мода")

    # Список модів
    sub.add_parser("list", help="Показати список встановлених модів")

    args = parser.parse_args()
    mgr = ModManager()

    if args.cmd == "set-path":
        mgr.state_mgr.game_path = args.path
        print(f"[+] Шлях до гри збережено: {mgr.state_mgr.game_path}")

    elif args.cmd == "add":
        mgr.install_from_archive(args.archive, args.name)

    elif args.cmd == "enable":
        mgr.enable_mod(args.name)

    elif args.cmd == "disable":
        mgr.disable_mod(args.name)

    elif args.cmd == "remove":
        mgr.remove_mod(args.name)

    elif args.cmd == "list":
        mods = mgr.state_mgr.state["mods"]
        print(f"Папка гри: {mgr.state_mgr.game_path}\n")
        if not mods:
            print("Модів ще не встановлено.")
            return
        for name, data in mods.items():
            status = "\033[92m[ON]\033[0m " if data["enabled"] else "\033[91m[OFF]\033[0m"
            print(f"{status} {name} ({len(data['links'])} активних файлів)")


if __name__ == "__main__":
    main()