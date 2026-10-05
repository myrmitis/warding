#!/usr/bin/env python3
"""Print the inside-out Developer ID signing order for a macOS .app bundle.

Apple notarization rejects a bundle unless EVERY nested Mach-O is signed with a
Developer ID identity, the hardened runtime, and a secure timestamp. The
Junction bundle carries far more nested code than an Electron shell: the
embedded Python backend under Contents/Resources ships an interpreter plus
hundreds of C-extension modules and vendored dylibs, and that set changes
whenever a Python dependency, the app name, or the Electron version does. So
the order is derived from the actual bundle at sign time rather than
maintained by hand.

codesign seals a bundle over the code inside it, so nested code has to be
signed before the bundle that contains it. The plan lists:

1. every Mach-O file that is not a symlink and not a bundle's main
   executable, deepest path first, then
2. every nested code bundle, deepest path first,

and leaves the top-level .app to the caller, which signs it last. A bundle's
main executable is signed by signing the bundle, which is also what binds it
to the bundle's Info.plist and sealed resources, so it is never signed as a
loose file. A code bundle is a directory with a bundle suffix whose Info.plist
names a CFBundleExecutable that exists; a directory that merely carries the
suffix is walked like any other, and the Mach-O files inside it are signed
individually.

Each output line is ``<kind>\\t<path relative to the .app>``, where kind is:

``exec``
    A Mach-O executable (MH_EXECUTE). Signed WITH the app entitlements: the
    hardened runtime reads entitlements from the executable that runs, which is
    how the embedded Python interpreter, ShipIt, and the helper executables get
    JIT and unsigned-executable-memory.
``code``
    Any other Mach-O (dylib, Python extension, .node addon, framework binary).
    Signed without entitlements, which the runtime ignores on loadable code.
``app``
    A nested .app bundle (the Electron helpers). Signed with the entitlements,
    which land on its main executable.
``bundle``
    Any other nested code bundle (.framework and friends). No entitlements.

Usage:
    signing-plan.py <path/to/App.app>

Exits 1 on a usage error. Paths never contain a tab or a newline in a bundle
electron-builder produces, which is what makes the line format unambiguous;
one that does fails the plan rather than being mis-split downstream.
"""

from __future__ import annotations

import os
import plistlib
import struct
import sys

# Directory suffixes codesign treats as sealed code bundles.
_BUNDLE_SUFFIXES = (".app", ".framework", ".appex", ".xpc", ".bundle", ".plugin")

# Mach-O magic numbers as read big-endian from the first four bytes. The
# MH_MAGIC forms mean a big-endian header, the MH_CIGAM forms little-endian.
_THIN_BIG_ENDIAN = {0xFEEDFACE, 0xFEEDFACF}
_THIN_LITTLE_ENDIAN = {0xCEFAEDFE, 0xCFFAEDFE}
# Universal (fat) headers are always big-endian. FAT_MAGIC_64 uses 64-bit arch
# records. 0xCAFEBABE is also the Java class-file magic; a plausible arch count
# is what tells the two apart (a class file's version field reads as >= 45).
_FAT_MAGIC = 0xCAFEBABE
_FAT_MAGIC_64 = 0xCAFEBABF
_MAX_FAT_ARCHS = 30
_FAT_ARCH_SIZE = 20
_FAT_ARCH_64_SIZE = 32

# mach_header.filetype for an executable (as opposed to a dylib, bundle, ...).
_MH_EXECUTE = 0x2

# Byte offset of mach_header.filetype: after magic, cputype and cpusubtype.
_FILETYPE_OFFSET = 12
_HEADER_PROBE_BYTES = 16


def _thin_filetype(head: bytes) -> int | None:
    """filetype of a thin Mach-O header, or None when ``head`` is not one."""
    if len(head) < _HEADER_PROBE_BYTES:
        return None
    (magic,) = struct.unpack(">I", head[:4])
    if magic in _THIN_BIG_ENDIAN:
        return int(struct.unpack_from(">I", head, _FILETYPE_OFFSET)[0])
    if magic in _THIN_LITTLE_ENDIAN:
        return int(struct.unpack_from("<I", head, _FILETYPE_OFFSET)[0])
    return None


def macho_filetype(path: str) -> int | None:
    """The Mach-O filetype of ``path``, or None when it is not a Mach-O.

    A universal binary reports the filetype of its first slice: every slice of
    a real build has the same one.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_HEADER_PROBE_BYTES)
            thin = _thin_filetype(head)
            if thin is not None:
                return thin
            if len(head) < 8:
                return None
            magic, nfat = struct.unpack(">II", head[:8])
            if magic not in (_FAT_MAGIC, _FAT_MAGIC_64) or not 0 < nfat < _MAX_FAT_ARCHS:
                return None
            record_size = _FAT_ARCH_64_SIZE if magic == _FAT_MAGIC_64 else _FAT_ARCH_SIZE
            fh.seek(8)
            record = fh.read(record_size)
            if len(record) < record_size:
                return None
            if magic == _FAT_MAGIC_64:
                (offset,) = struct.unpack_from(">Q", record, 8)
            else:
                (offset,) = struct.unpack_from(">I", record, 8)
            fh.seek(offset)
            return _thin_filetype(fh.read(_HEADER_PROBE_BYTES))
    except OSError:
        return None


def _bundle_executable(plist_path: str, exe_dir: str) -> str | None:
    """The main executable an Info.plist names, when it exists under exe_dir."""
    if not os.path.isfile(plist_path):
        return None
    try:
        with open(plist_path, "rb") as fh:
            name = plistlib.load(fh).get("CFBundleExecutable")
    except Exception:
        return None
    if not isinstance(name, str) or not name:
        return None
    exe = os.path.join(exe_dir, name)
    return exe if os.path.isfile(exe) and not os.path.islink(exe) else None


def main_executables(bundle: str) -> list[str]:
    """Main executables of a code bundle; empty when it is not one.

    Covers the three layouts codesign signs as bundles: Contents/ (apps and
    the other Contents-style bundles), versioned frameworks
    (Versions/<v>/Resources/Info.plist, executable in Versions/<v>/), and flat
    frameworks (Resources/Info.plist or Info.plist, executable at the root).
    Versions/Current is a symlink to a real version directory and is skipped
    so a framework is not counted twice.
    """
    found: list[str] = []
    contents = os.path.join(bundle, "Contents")
    exe = _bundle_executable(os.path.join(contents, "Info.plist"), os.path.join(contents, "MacOS"))
    if exe:
        found.append(exe)
    versions = os.path.join(bundle, "Versions")
    if os.path.isdir(versions) and not os.path.islink(versions):
        for name in sorted(os.listdir(versions)):
            version_dir = os.path.join(versions, name)
            if os.path.islink(version_dir) or not os.path.isdir(version_dir):
                continue
            exe = _bundle_executable(
                os.path.join(version_dir, "Resources", "Info.plist"), version_dir
            )
            if exe:
                found.append(exe)
    for plist in (
        os.path.join(bundle, "Resources", "Info.plist"),
        os.path.join(bundle, "Info.plist"),
    ):
        exe = _bundle_executable(plist, bundle)
        if exe:
            found.append(exe)
    return found


def _depth_first(paths: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Deepest relative path first; ties broken by path for a stable order."""
    return sorted(paths, key=lambda entry: (-entry[1].count("/"), entry[1]))


def plan(app_path: str) -> list[tuple[str, str]]:
    """(kind, relative path) pairs in signing order, the top-level app excluded."""
    bundles: list[tuple[str, str]] = []
    # Signed through their bundle, never as loose files. The top-level app's
    # own executable is included: the caller signs that bundle last.
    bundle_executables = {os.path.realpath(p) for p in main_executables(app_path)}
    macho_files: list[tuple[str, str]] = []
    for root, dirs, names in os.walk(app_path):
        for name in dirs:
            full = os.path.join(root, name)
            if os.path.islink(full) or not name.endswith(_BUNDLE_SUFFIXES):
                continue
            executables = main_executables(full)
            if executables:
                bundle_executables.update(os.path.realpath(p) for p in executables)
                kind = "app" if name.endswith(".app") else "bundle"
                bundles.append((kind, os.path.relpath(full, app_path)))
        for name in names:
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            filetype = macho_filetype(full)
            if filetype is None:
                continue
            kind = "exec" if filetype == _MH_EXECUTE else "code"
            macho_files.append((kind, full))
    files = [
        (kind, os.path.relpath(full, app_path))
        for kind, full in macho_files
        if os.path.realpath(full) not in bundle_executables
    ]
    return _depth_first(files) + _depth_first(bundles)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <App.app>", file=sys.stderr)
        return 1
    app_path = argv[1]
    if not os.path.isdir(app_path):
        print(f"ERROR: .app not found at {app_path}", file=sys.stderr)
        return 1
    entries = plan(app_path)
    for kind, rel in entries:
        if "\t" in rel or "\n" in rel:
            print(f"ERROR: unsupported character in bundle path {rel!r}", file=sys.stderr)
            return 1
        print(f"{kind}\t{rel}")
    counts: dict[str, int] = {}
    for kind, _rel in entries:
        counts[kind] = counts.get(kind, 0) + 1
    summary = ", ".join(
        f"{counts.get(kind, 0)} {kind}" for kind in ("exec", "code", "app", "bundle")
    )
    print(f"signing plan: {len(entries)} nested code objects ({summary})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
