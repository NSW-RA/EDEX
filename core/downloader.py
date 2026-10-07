"""Filename handling and zip bundling for downloaded attachments.

Pure helpers (no Playwright, no disk side effects beyond the explicit zip
builder) so they can be unit-tested. The actual authenticated GET happens in
core.browser, which reuses the signed-in browser context.
"""

from __future__ import annotations

import io
import re
import zipfile
from email.message import Message
from pathlib import Path

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "attachment") -> str:
    """Strip path separators and characters Windows/most filesystems reject.

    Trailing dots and spaces are removed (Windows rejects them), and the result
    is capped to a sane length. Returns `fallback` when nothing usable remains.
    """
    name = name.strip().replace("\n", " ").replace("\r", " ")
    name = _UNSAFE.sub("_", name)
    name = name.strip(" .")
    if len(name) > 180:
        stem, dot, ext = name.rpartition(".")
        name = (stem[:170] + dot + ext) if dot else name[:180]
    return name or fallback


def filename_from_content_disposition(header: str | None) -> str | None:
    """Extract a filename from a Content-Disposition header, or None.

    Handles both `filename="x.pdf"` and RFC 5987 `filename*=UTF-8''x.pdf`.
    Uses the stdlib email parser so quoting and encoding are handled for us.
    """
    if not header:
        return None
    msg = Message()
    msg["content-disposition"] = header
    # get_filename understands filename* (RFC 5987) and quoted filename.
    value = msg.get_filename()
    return value or None


def dedupe_names(names: list[str]) -> list[str]:
    """Make a list of filenames unique by suffixing ' (2)', ' (3)', ... on clashes.

    Comparison is case-insensitive so 'File.PDF' and 'file.pdf' don't collide on
    a case-insensitive filesystem. Order is preserved.
    """
    out: list[str] = []
    used: set[str] = set()
    for name in names:
        candidate = name
        if candidate.lower() not in used:
            out.append(candidate)
            used.add(candidate.lower())
            continue
        stem, dot, ext = name.rpartition(".")
        base = stem if dot else name
        suffix = ext if dot else ""
        n = 2
        while True:
            candidate = f"{base} ({n}){('.' + suffix) if suffix else ''}"
            if candidate.lower() not in used:
                break
            n += 1
        out.append(candidate)
        used.add(candidate.lower())
    return out


def build_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Bundle (filename, bytes) pairs into a single in-memory zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buffer.getvalue()


def _safe_folder(folder: str) -> str:
    """Sanitise each path segment of a folder, preserving the '/' separators."""
    parts = [safe_filename(p, "folder") for p in folder.split("/") if p.strip()]
    return "/".join(parts)


def _layout_tree(entries: list[tuple[str, str, bytes]]) -> list[tuple[str, bytes]]:
    """Resolve (folder, name, bytes) into (relative_path, bytes), de-duplicating
    filenames *within each folder* only.

    Two files sharing a name in different folders (e.g. the same '1.jpeg' under
    two damage items) are both kept, each in its own folder.
    """
    by_folder: dict[str, list[tuple[str, bytes]]] = {}
    for folder, name, data in entries:
        by_folder.setdefault(_safe_folder(folder), []).append((name, data))

    laid_out: list[tuple[str, bytes]] = []
    for folder, items in by_folder.items():
        names = dedupe_names([safe_filename(n) for n, _ in items])
        for (_orig, data), final in zip(items, names):
            rel = f"{folder}/{final}" if folder else final
            laid_out.append((rel, data))
    return laid_out


def build_tree_zip(
    entries: list[tuple[str, str, bytes]], empty_folders: list[str] | None = None
) -> bytes:
    """Bundle (folder, filename, bytes) into a zip laid out as folder/filename.

    `empty_folders` names folders that must exist in the zip even when they hold
    no files (e.g. the always-present "Completion" folder). Each is written as a
    directory entry so it survives unzipping.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in empty_folders or []:
            safe = _safe_folder(folder)
            if safe:
                zf.writestr(safe + "/", b"")
        for rel, data in _layout_tree(entries):
            zf.writestr(rel, data)
    return buffer.getvalue()


def write_tree(entries: list[tuple[str, str, bytes]], dest_root: str) -> list[str]:
    """Write (folder, filename, bytes) as an on-disk folder tree under dest_root.

    Creates sub-folders as needed, de-duplicates names within each folder, and
    returns the list of absolute paths written. Used by the local "save to a
    folder" option so the user gets the tree without unzipping.
    """
    root = Path(dest_root).expanduser()
    written: list[str] = []
    for rel, data in _layout_tree(entries):
        target = root.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(str(target))
    return written
