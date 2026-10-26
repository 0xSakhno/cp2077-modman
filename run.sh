#!/bin/sh
# SPDX-License-Identifier: MIT
# Launch the Cyberpunk 2077 Mod Manager from any working directory.
set -eu

SOURCE=$0
while [ -L "$SOURCE" ]; do
    SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$SOURCE")" && pwd -P)
    LINK_TARGET=$(readlink "$SOURCE") || {
        printf '[modman] Cannot resolve launcher symlink.\n' >&2
        exit 1
    }
    case "$LINK_TARGET" in
        /*) SOURCE=$LINK_TARGET ;;
        *) SOURCE=$SOURCE_DIR/$LINK_TARGET ;;
    esac
done
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$SOURCE")" && pwd -P)
VENV_DIR=$APP_DIR/.venv
REQUIREMENTS=$APP_DIR/requirements.txt
PYTHON_BIN=${PYTHON:-python3}

log() { printf '[modman] %s\n' "$*"; }
die() { printf '[modman] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'HELP'
Cyberpunk 2077 Mod Manager — Linux launcher

Usage:
  ./run.sh               Launch the graphical mod manager
  ./run.sh --setup       Create/prepare the local Python environment only
  ./run.sh --check       Show prerequisite status without changing files
  ./run.sh --help        Show this help

First launch creates .venv beside this script and installs Python GUI
dependencies from requirements.txt when needed (internet may be required).
System libarchive must be installed separately to import mod archives.
Use PYTHON=/path/to/python3.14 to select another Python interpreter.
HELP
}

check_python() {
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        die "Python 3 was not found. Install Python 3.11+ or set PYTHON."
    fi
    if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        die "Python 3.11 or newer is required (currently: $PYTHON_BIN)."
    fi
}

setup_environment() {
    check_python
    [ -f "$REQUIREMENTS" ] || die "Missing requirements.txt in $APP_DIR."
    [ -f "$APP_DIR/gui.py" ] || die "Missing gui.py in $APP_DIR."

    if [ ! -x "$VENV_DIR/bin/python" ]; then
        log "Creating the virtual environment in $VENV_DIR..."
        "$PYTHON_BIN" -m venv "$VENV_DIR" ||
            die "Could not create the virtual environment. Install python3-venv if necessary."
    fi

    if ! "$VENV_DIR/bin/python" -c '
import sys
from importlib.metadata import version
from PySide6.QtWidgets import QApplication
major, minor = [int(x) for x in version("PySide6").split(".")[:2]]
sys.exit(0 if (6, 8) <= (major, minor) < (7, 0) else 1)
' >/dev/null 2>&1; then
        log "Installing GUI dependencies into the local virtual environment..."
        "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS" ||
            die "Dependency installation failed. Check network access and Python/Qt compatibility."
    fi
}

check_environment() {
    check_python
    log "Python: $("$PYTHON_BIN" --version 2>&1)"
    if "$PYTHON_BIN" -c 'import ctypes.util, sys; sys.exit(0 if ctypes.util.find_library("archive") else 1)' >/dev/null 2>&1; then
        log "libarchive: found"
    else
        log "libarchive: not found (mod archive installation will be unavailable)"
    fi
    if [ -x "$VENV_DIR/bin/python" ]; then
        log "Local Python environment: present"
    else
        log "Local Python environment: not initialized (created on first launch)"
    fi
}

case "${1:-}" in
    --help|-h)
        usage
        ;;
    --check)
        check_environment
        ;;
    --setup)
        setup_environment
        log "Environment ready. Run ./run.sh to start the GUI."
        ;;
    "")
        setup_environment
        cd "$APP_DIR"
        exec "$VENV_DIR/bin/python" "$APP_DIR/gui.py"
        ;;
    *)
        die "Unknown argument: $1. Run ./run.sh --help for usage."
        ;;
esac
