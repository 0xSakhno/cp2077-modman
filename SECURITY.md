# Archive extraction security

Cyberpunk Mod Manager deploys user-selected mod archives into a private temporary
workspace before publishing them to the manager's mod store. Archive contents
must be treated as **untrusted**.

## Supported inputs

The extractor reads archives through the local **libarchive** shared library.
This is the same library commonly installed for bsdtar and supports formats
including ZIP, 7z, RAR and TAR, depending on your distribution's build.

If the library is unavailable, installation fails with a clear error instead
of switching to an unsafe extraction fallback. Install your distribution's
libarchive runtime to enable mod installation.

## Safeguards

The extractor in core/normalizer.py:

- Streams each archive entry through libarchive and writes regular-file bytes
  directly; it never invokes an archiver to write arbitrary paths.
- Rejects absolute paths, parent traversal (..), Windows drive prefixes,
  backslashes, control characters, oversized names and duplicate paths.
- Rejects symbolic links, hard links, device files, FIFOs and other special
  archive entries.
- Creates only regular files and directories in the temporary workspace, using
  exclusive file creation so that an archive entry cannot overwrite another.
- Limits archives to 50,000 entries, 4 GiB per file and 8 GiB of total
  uncompressed data. These are conservative defaults.
- Removes the partial extraction directory if validation or decompression fails.
- Registers/deploys the mod only after extraction and normalisation succeed.

Normal game deployment still uses ownership-checked symlinks and is separate
from archive extraction.

## Compatibility notes

- Archives containing symbolic links or hard links are intentionally refused,
  even if those links were legitimate.
- Files outside known Cyberpunk 2077 mod layouts may not be deployed by the
  normaliser.
- Large mod packs may require reviewed adjustments to the extraction limits.
- 7z/RAR support depends on the codecs compiled into your system libarchive.

## Threats not covered

Archive validation does not establish that **the mod itself is trustworthy**.
A mod can include malicious or broken game scripts or DLLs without using a
malicious archive path. Only install mods from sources you trust.

The extractor is designed to stop crafted archive entries from escaping their
temporary workspace. It is not a defence against another local process that
can concurrently modify that workspace or against vulnerabilities in the
system's libarchive decoder itself.

Crash/power-loss recovery and stronger durability guarantees for deployments
remain future work. Before advertising a stable release, test installation,
disabling and restoration on a real target Linux environment and verify the
archive codecs supplied by the system libarchive build.

## Tests

Run the security and deployment tests:

    python -m unittest discover -s tests -v

The GitHub Actions matrix also runs these tests on Python 3.11 and 3.14.
