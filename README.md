# Cyberpunk 2077 Mod Manager

**A Linux-native, symlink-based mod manager for Cyberpunk 2077.**

[![Deployment and UI checks](https://github.com/SanyaCatMeow/cp2077-modman/actions/workflows/core-tests.yml/badge.svg)](https://github.com/SanyaCatMeow/cp2077-modman/actions/workflows/core-tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Manage your mods without copying an entire mod collection into the game directory. The application offers a Night City-inspired desktop interface, per-mod integrity checks, conflict-aware deployment and Steam/Proton integration.

> [!IMPORTANT]
> **Early-access preview.** This project is under active development, has been tested primarily with Cyberpunk 2077 on Linux via Steam/Proton, and is not affiliated with CD PROJEKT RED, Valve or Nexus Mods. Make backups and close the game before modifying its files. This is not a stable, crash-proof package manager.

## Features

- **Mod library** — install, enable, disable and delete individual mods, or enable/disable all; search and filter by state.
- **Safe symlink deployment** — keep mod files in a separate local store and link them into your game installation.
- **Conflict checks** — block collisions with files owned by other enabled mods and avoid overwriting foreign symlinks.
- **Vanilla file preservation** — move existing game files to adjacent `.vanilla_bak` files before deploying links when necessary, and restore them when safely disabling mods.
- **Mod Health Check** — identify healthy, repairable and manually blocked deployments. Inspect details in the library and activity log.
- **Manual Safe Repair** — recreate missing symlinks or replace regular-file copies only when their contents are identical to the stored mod originals. Never download or silently replace modified files.
- **Archive validation** — stream files through libarchive and reject unsafe paths, symlinks, hardlinks, special files and oversized extractions.
- **Dependency hints** — detect probable requirements for Redscript, Cyber Engine Tweaks (CET), RED4ext, ArchiveXL and TweakXL.
- **Steam/Proton helpers** — detect a Proton prefix, inspect/configure DLL overrides and launch Cyberpunk 2077 with mod-related options.
- **English-language PySide6 GUI**, drag-and-drop archive installation, resizable activity log and an optional CLI.
- **Simple Linux launchers:** one-command `./run.sh` setup/startup, plus optional desktop-menu integration.

## Requirements

- **Linux** (desktop environment with Qt support). The primary workflow targets Steam + Proton.
- **Python 3.11 or newer** (tested in CI on Python 3.11 and 3.14).
- **PySide6** (installed using the steps below).
- **System libarchive runtime** (needed to install mods from archives).
- A **legitimate installed copy of Cyberpunk 2077**. The game and mods are **not included**.

The library reader supports ZIP, 7z, RAR and TAR-family archives to the extent supported by your distribution's libarchive build. The GUI file picker and drag-and-drop accept `.zip`, `.7z`, `.rar` and `.tar.gz`. Some individual mod archives may need manual repackaging or may not be compatible with the manager.

### Install and launch on Linux

Install the system **libarchive** runtime using your distribution's package manager (`libarchive` on Arch/Fedora, `libarchive13` or `libarchive13t64` on Debian/Ubuntu variants).

Clone the project, then start it with the included **executable launcher**:

```bash
git clone https://github.com/SanyaCatMeow/cp2077-modman.git
cd cp2077-modman
./run.sh
```

On first launch, `run.sh` checks for Python 3.11+, creates a local `.venv` and installs PySide6 from `requirements.txt` if necessary. Internet access is needed for the first dependency installation; later launches reuse the virtual environment. The launcher does not alter your mods, game files or Steam configuration.

Additional commands:

```bash
./run.sh --check        # Show prerequisites; no files changed
./run.sh --setup        # Prepare Python without launching the GUI
./run.sh --help         # Show launcher options
```

You can select a Python interpreter using `PYTHON=python3.14 ./run.sh`. If executable permissions were lost while transferring files, `sh run.sh` works too.

#### Optional desktop application shortcut

To put **Cyberpunk 2077 Mod Manager** in your Linux desktop application's menu:

```bash
./install-desktop.sh
```

This runs the one-time Python setup and installs a per-user desktop entry under `${XDG_DATA_HOME:-~/.local/share}/applications/`. No root permissions are needed. The shortcut points to the repository location and uses your system's generic games icon.

Remove it with:

```bash
./install-desktop.sh --uninstall
```

If you move the cloned repository, rerun the installer to update the shortcut.

#### Manual Python setup (alternative)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python gui.py
```

Missing system Qt libraries such as `libEGL.so.1` require the appropriate EGL/OpenGL packages from your Linux distribution; Python packages cannot supply every native Qt runtime dependency.

## Quick start

1. **Close Cyberpunk 2077.** On first launch, the manager tries to find the game in your Steam libraries. Verify the **Game Directory** path; use **Browse** or **Auto-detect** if necessary.
2. Select **Install Mod** or drag a supported archive onto the window. The archive is checked, normalized and stored in the local mod library. If deployment passes its checks, the mod is enabled.
3. Use the toggle next to a mod to enable or disable it, or use the bulk actions.
4. Select **Verify Integrity** to audit the deployment state. The **Health** column and mod inspector provide additional context.
5. For an enabled mod marked **REPAIR**, select **Repair Mod** and review the confirmation before proceeding. Modified files, foreign links, unsafe sources and conflicting backups are not automatically repaired.
6. Use **Steam Settings** to inspect Proton DLL overrides and suggested launch options. Then launch the game from the manager or your normal Steam installation.

**Important:** The manager does not install prerequisite frameworks for you or check that a mod supports your particular game patch. Read each mod author's instructions.

### Steam/Proton setup

For setups that require native `version.dll` and `winmm.dll`, the recommended Steam launch options are:

```text
WINEDLLOVERRIDES="version=n,b;winmm=n,b" %command% --launcher-skip -modded
```

You can copy these options from the **Steam Settings** dialog. If the application updates your Proton prefix's `user.reg`, it creates a `user.reg.bak` backup when one is not already present. Check that the correct Proton prefix was detected before applying settings.

Steam launch integration is intended for Steam-installed copies of the game. Other launchers may require their own launch setup.

## Command-line interface

You can use the basic command-line interface instead of the GUI:

```bash
python main.py list
python main.py set-path "/path/to/Cyberpunk 2077"
python main.py add "/path/to/mod.zip"
python main.py add "/path/to/mod.7z" --name "My Mod"
python main.py enable "My Mod"
python main.py disable "My Mod"
python main.py remove "My Mod"
```

**Warning:** `remove` deletes that mod's local files after safely disabling it. It does not delete your game saves.

## How deployment works

Mod files live in a separate manager-owned directory. When enabled, each file is linked into the corresponding relative path under your Cyberpunk 2077 game directory.

```text
~/.local/share/cp2077-modman/mods/Example Mod/r6/scripts/example.reds
                                |
                                | symlink
                                v
<Game directory>/r6/scripts/example.reds
```

A symlink is a reference to the original stored file, **not an independent copy**. Modifying a deployed file through its symlink can therefore also modify the manager's stored copy.

The manager keeps application data here:

| Path | Purpose |
| --- | --- |
| `~/.local/share/cp2077-modman/state.json` | Installed mods, deployment state and game path |
| `~/.local/share/cp2077-modman/mods/` | Stored mod files |
| `~/.local/share/cp2077-modman/tmp/` | Temporary installation workspaces |
| `<game file>.vanilla_bak` | Backup of a pre-existing file if a link replaces it |

Avoid manually deleting manager-owned files or backup files. If another mod, the game or a reset utility replaces/removes a deployed link, **Verify Integrity** will help identify the issue. **Repair Mod** does not fetch original files from Nexus Mods or other websites.

## Supported mod layouts

The archive normalizer recognizes common Cyberpunk 2077 roots, including `archive/`, `bin/`, `r6/`, `red4ext/`, `mods/` and `engine/`. Standalone `.archive`, `.xl`, `.reds`, `.yaml` and `.yml` files may be routed to conventional game paths.

**Not all mod installers are supported.** Archives requiring a custom installer, installation choices, executable scripts or special manual steps may need to be installed outside this manager. Archive symlinks and hardlinks are rejected by design.

## Safety and current limitations

Read [SECURITY.md](SECURITY.md) for the extraction threat model and limits.

- The manager validates **archive structure**, not whether a mod's scripts or native DLLs are trustworthy.
- It does **not** download, update or authenticate mods from Nexus Mods or other mod sites.
- Safe Repair only works if the original mod file is still present in the local store.
- Interrupted filesystem operations during a crash or power failure are **not yet transactionally recoverable**; back up files before major changes.
- Archive codec compatibility, especially RAR/7z on different distributions, requires more real-world testing.
- Dependency detection is heuristic, not a substitute for checking each mod's documentation.

## Testing

Run the deployment and archive-security unit tests:

```bash
python -m unittest discover -s tests -v
```

An optional isolated Qt smoke test exercises the GUI without touching your real game or mod library:

```bash
QT_QPA_PLATFORM=offscreen python tests/gui_smoke.py
```

GitHub Actions runs core tests on Python 3.11 and 3.14 and a headless Qt GUI smoke test. GUI preview screenshots are available as artifacts in the workflow runs.

## Contributing and project status

Bug reports, Linux distribution compatibility results and pull requests are welcome through [GitHub Issues](https://github.com/SanyaCatMeow/cp2077-modman/issues).

Please include your Linux distribution, Python/PySide6 versions, game patch, archive format and a sanitized log when reporting bugs. Do not upload proprietary game files or paid mod content.

**License:** [MIT](LICENSE) — Copyright © 2026 SanyaCatMeow. You may use, study, modify, redistribute and even sell copies of this software, as long as the license and copyright notice are included. The software is provided without warranty.

---

*Built for Night City. Designed for Linux.*
