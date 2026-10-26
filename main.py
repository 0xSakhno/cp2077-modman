#!/usr/bin/env python3
import argparse
from core.linker import ModManager


def main():
    parser = argparse.ArgumentParser(description="Cyberpunk 2077 Linux Mod Manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Configure the game directory
    p_path = sub.add_parser("set-path", help="Set the Cyberpunk 2077 installation directory")
    p_path.add_argument("path", help="Absolute path to the game's root directory")

    # Install mod archives
    p_add = sub.add_parser("add", help="Install a mod from an archive (.zip, .7z, .rar, .tar.gz)")
    p_add.add_argument("archive", help="Path to the archive")
    p_add.add_argument("--name", help="Optional custom mod name", default=None)

    # Enable, disable and remove mods
    p_en = sub.add_parser("enable", help="Enable a mod")
    p_en.add_argument("name", help="Exact mod name")

    p_dis = sub.add_parser("disable", help="Disable a mod")
    p_dis.add_argument("name", help="Exact mod name")

    p_rm = sub.add_parser("remove", help="Permanently remove a mod")
    p_rm.add_argument("name", help="Exact mod name")

    # List installed mods
    sub.add_parser("list", help="List installed mods")

    args = parser.parse_args()
    mgr = ModManager()

    if args.cmd == "set-path":
        mgr.state_mgr.game_path = args.path
        print(f"[+] Game directory saved: {mgr.state_mgr.game_path}")

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
        print(f"Game directory: {mgr.state_mgr.game_path}\n")
        if not mods:
            print("No mods installed yet.")
            return
        for name, data in mods.items():
            status = "\033[92m[ON]\033[0m " if data["enabled"] else "\033[91m[OFF]\033[0m"
            print(f"{status} {name} ({len(data['links'])} active files)")


if __name__ == "__main__":
    main()