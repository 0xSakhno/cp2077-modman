#!/bin/sh
# SPDX-License-Identifier: MIT
# Optional per-user application-menu integration.
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
APPLICATIONS_DIR=$DATA_HOME/applications
DESKTOP_FILE=$APPLICATIONS_DIR/cp2077-modman.desktop

log() { printf '[modman] %s\n' "$*"; }
die() { printf '[modman] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'HELP'
Cyberpunk 2077 Mod Manager — desktop shortcut

Usage:
  ./install-desktop.sh             Install a launcher in your app menu
  ./install-desktop.sh --uninstall Remove the installed launcher
  ./install-desktop.sh --help      Show this help

Installation prepares the local Python environment first. No system files,
game files or mod files are modified. Keep the repository at the same path
after installation, or reinstall the desktop shortcut.
HELP
}

refresh_menu() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
    fi
}

case "${1:-}" in
    --help|-h)
        usage
        exit 0
        ;;
    --uninstall)
        if [ -f "$DESKTOP_FILE" ]; then
            rm -- "$DESKTOP_FILE"
            refresh_menu
            log "Removed the desktop shortcut."
        else
            log "No desktop shortcut is installed."
        fi
        exit 0
        ;;
    ""|--install)
        ;;
    *)
        die "Unknown argument: $1. Run ./install-desktop.sh --help for usage."
        ;;
esac

# A desktop Exec field reserves percent signs and quotation characters.
# Reject unusual paths instead of writing a malformed launcher.
case "$APP_DIR" in
    *\"*|*\\*|*%*)
        die "Repository path contains characters not supported by this desktop launcher."
        ;;
esac

[ -f "$APP_DIR/run.sh" ] || die "Cannot find run.sh in the same directory."
/bin/sh "$APP_DIR/run.sh" --setup ||
    die "Setup failed. The desktop launcher was not installed."

mkdir -p -- "$APPLICATIONS_DIR"
TEMP_FILE=$(mktemp "$APPLICATIONS_DIR/.cp2077-modman.XXXXXXXX") ||
    die "Cannot create the desktop shortcut."
trap 'rm -f -- "$TEMP_FILE"' 0
trap 'exit 1' 1 2 3 15

cat > "$TEMP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Cyberpunk 2077 Mod Manager
GenericName=Game Mod Manager
Comment=Manage Cyberpunk 2077 mods on Linux
Exec=/bin/sh "$APP_DIR/run.sh"
Path=$APP_DIR
Icon=applications-games
Terminal=false
Categories=Game;Utility;
StartupNotify=true
EOF

chmod 644 "$TEMP_FILE"
mv -f -- "$TEMP_FILE" "$DESKTOP_FILE"
refresh_menu
log "Installed desktop shortcut: $DESKTOP_FILE"
log "Look for 'Cyberpunk 2077 Mod Manager' in your application menu."
