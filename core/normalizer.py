"""Secure extraction and layout normalisation of third-party mod archives."""

import ctypes
import ctypes.util
import os
import shutil
import stat
from pathlib import Path, PurePosixPath

# Cyberpunk 2077 game directory roots recognised by the normaliser.
KNOWN_ROOT_DIRS = {"archive", "bin", "r6", "red4ext", "mods", "engine"}

EXT_ROUTING = {
    ".archive": Path("archive/pc/mod"),
    ".xl": Path("archive/pc/mod"),
    ".reds": Path("r6/scripts"),
    ".yaml": Path("r6/tweaks"),
    ".yml": Path("r6/tweaks"),
}

# Maximum uncompressed sizes. These values can be adjusted for large mod packs.
MAX_ARCHIVE_ENTRIES = 50_000
MAX_SINGLE_FILE_BYTES = 4 * 1024**3
MAX_TOTAL_EXTRACTED_BYTES = 8 * 1024**3
MAX_ARCHIVE_PATH_BYTES = 4096
_READ_CHUNK_SIZE = 1024 * 1024


def _archive_library():
    """Bind the system libarchive used by bsdtar (ZIP, 7z, RAR, TAR, etc.)."""
    library_name = ctypes.util.find_library("archive")
    if not library_name:
        raise RuntimeError("libarchive was not found. Install the system libarchive package.")
    lib = ctypes.CDLL(library_name)

    signatures = {
        "archive_read_new": (ctypes.c_void_p, []),
        "archive_read_support_filter_all": (ctypes.c_int, [ctypes.c_void_p]),
        "archive_read_support_format_all": (ctypes.c_int, [ctypes.c_void_p]),
        "archive_read_open_filename": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]),
        "archive_read_next_header": (ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]),
        "archive_read_data": (ctypes.c_ssize_t, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]),
        "archive_read_free": (ctypes.c_int, [ctypes.c_void_p]),
        "archive_error_string": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_entry_pathname": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_entry_filetype": (ctypes.c_uint, [ctypes.c_void_p]),
        "archive_entry_size": (ctypes.c_int64, [ctypes.c_void_p]),
        "archive_entry_symlink": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_entry_hardlink": (ctypes.c_char_p, [ctypes.c_void_p]),
    }
    for name, (restype, argtypes) in signatures.items():
        fn = getattr(lib, name)
        fn.restype = restype
        fn.argtypes = argtypes
    return lib


def _safe_member_path(name: str):
    """Return a safe POSIX relative path, or None for the archive root."""
    if not name or len(os.fsencode(name)) > MAX_ARCHIVE_PATH_BYTES:
        raise ValueError("Archive entry has an empty or excessively long path.")
    if name.startswith(("/", "\\")) or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError(f"Archive path contains control characters: {name!r}")
    parts = name.split("/")
    if ".." in parts or (parts[0] and ":" in parts[0]):
        raise ValueError(f"Archive path escapes the extraction directory: {name!r}")
    clean = tuple(part for part in parts if part not in ("", "."))
    return PurePosixPath(*clean) if clean else None


def extract_archive(archive_path: Path, extract_to: Path):
    """Extract untrusted archives using libarchive's streaming reader.

    Never ask an external archiver to write paths to disk. Every member is
    validated first, then its bytes are copied into a fresh private staging
    directory. Symbolic links, hard links, special files, duplicate entries,
    absolute/parent-traversal paths and oversized payloads are refused.
    """
    archive_path = Path(archive_path)
    extract_to = Path(extract_to)
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    if extract_to.is_symlink():
        raise ValueError("Extraction destination cannot be a symbolic link.")
    if extract_to.exists():
        shutil.rmtree(extract_to)
    extract_to.mkdir(parents=True)

    reader = None
    lib = None
    try:
        lib = _archive_library()
        reader = lib.archive_read_new()
        if not reader:
            raise RuntimeError("Could not initialize libarchive reader.")
        lib.archive_read_support_filter_all(reader)
        lib.archive_read_support_format_all(reader)
        result = lib.archive_read_open_filename(reader, os.fsencode(archive_path), 10240)
        if result != 0:
            error = lib.archive_error_string(reader)
            raise ValueError(f"Unable to open archive: {os.fsdecode(error or b'unknown error')}")

        seen = set()
        entry_count = 0
        total_bytes = 0
        chunk = ctypes.create_string_buffer(_READ_CHUNK_SIZE)
        while True:
            entry = ctypes.c_void_p()
            status = lib.archive_read_next_header(reader, ctypes.byref(entry))
            if status == 1:  # ARCHIVE_EOF
                break
            if status != 0:  # ARCHIVE_OK
                error = lib.archive_error_string(reader)
                raise ValueError(f"Invalid or corrupted archive: {os.fsdecode(error or b'unknown error')}")

            entry_count += 1
            if entry_count > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Archive exceeds the maximum number of entries.")
            raw_name = lib.archive_entry_pathname(entry)
            if raw_name is None:
                raise ValueError("Archive entry has no filename.")
            name = os.fsdecode(raw_name)
            relative = _safe_member_path(name)

            kind = lib.archive_entry_filetype(entry)
            if (lib.archive_entry_symlink(entry) is not None
                    or lib.archive_entry_hardlink(entry) is not None
                    or kind not in (stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"Unsupported or unsafe archive entry type: {name!r}")
            if relative is None:
                if kind == stat.S_IFDIR:
                    continue  # Harmless root directory entry, e.g. './'
                raise ValueError("Archive file entry has no relative path.")

            # Fail closed on duplicate paths rather than allowing overwrite.
            if relative in seen:
                raise ValueError(f"Duplicate archive path: {name!r}")
            seen.add(relative)

            target = extract_to.joinpath(*relative.parts)
            if kind == stat.S_IFDIR:
                target.mkdir(parents=True, exist_ok=True)
                continue

            announced_size = lib.archive_entry_size(entry)
            if announced_size > MAX_SINGLE_FILE_BYTES:
                raise ValueError(f"Archive entry exceeds the per-file size limit: {name!r}")
            if announced_size >= 0 and total_bytes + announced_size > MAX_TOTAL_EXTRACTED_BYTES:
                raise ValueError("Archive exceeds the total extraction size limit.")

            target.parent.mkdir(parents=True, exist_ok=True)
            file_bytes = 0
            with target.open("xb") as output:
                while True:
                    count = lib.archive_read_data(reader, chunk, len(chunk))
                    if count == 0:
                        break
                    if count < 0:
                        error = lib.archive_error_string(reader)
                        raise ValueError(f"Failed to read archive entry {name!r}: {os.fsdecode(error or b'unknown error')}")
                    file_bytes += count
                    total_bytes += count
                    if (file_bytes > MAX_SINGLE_FILE_BYTES
                            or total_bytes > MAX_TOTAL_EXTRACTED_BYTES):
                        raise ValueError("Archive exceeds the total extraction size limit.")
                    output.write(chunk.raw[:count])
    except Exception:
        # Never expose partially extracted archives to the normaliser.
        shutil.rmtree(extract_to)
        raise
    finally:
        if reader and lib:
            lib.archive_read_free(reader)


def normalize_mod_structure(raw_dir: Path, target_mod_dir: Path):
    """
    Builds a clean game-relative directory layout from an extracted archive.
    """
    if target_mod_dir.exists():
        shutil.rmtree(target_mod_dir)
    target_mod_dir.mkdir(parents=True, exist_ok=True)

    # 1. Locate recognized game-root directories (bin, r6, archive, etc.)
    found_roots = []
    for path in raw_dir.rglob("*"):
        if path.is_dir() and path.name.lower() in KNOWN_ROOT_DIRS:
            # Ignore directories nested inside another known root
            if not any(p in path.parents for p in found_roots):
                found_roots.append(path)

    if found_roots:
        # Copy recognized directory trees into the normalized mod layout
        for root_folder in found_roots:
            dest = target_mod_dir / root_folder.name.lower()
            shutil.copytree(root_folder, dest, dirs_exist_ok=True)
        return

    # 2. Route individual mod files when no known game-root directory exists
    for file_path in raw_dir.rglob("*"):
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext in EXT_ROUTING:
                rel_dir = EXT_ROUTING[ext]
                # Keep scripts and tweaks in a mod-specific subdirectory
                if ext in {".reds", ".yaml", ".yml"}:
                    dest_dir = target_mod_dir / rel_dir / target_mod_dir.name
                else:
                    dest_dir = target_mod_dir / rel_dir

                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_dir / file_path.name)