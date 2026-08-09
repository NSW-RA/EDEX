"""Plain data structures passed between the browser worker and the UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Attachment:
    """One downloadable link discovered on a page.

    `url` is absolute. `text` is the link's visible label (may be empty).
    `filename` is our best guess at a file name, derived from the link text or
    the URL path; it is refined from the Content-Disposition header at download
    time. `ext` is the lower-case extension without the dot ("pdf"), or "".
    `is_file` is True when the link looks like a real attachment (its text or
    URL names a file, or the URL is a download endpoint) rather than page
    navigation — used to hide nav links from the download list by default.
    """

    url: str
    text: str
    filename: str
    ext: str
    is_file: bool = False


@dataclass(frozen=True)
class CategorisedFile:
    """An attachment placed in the damage-item / category folder tree.

    `group` is the top folder — a damage item ("Damage 01 — CBRS1 (Carrowbrook
    Road)") or "Application-level". `category` is the sub folder ("Pre-Disaster
    Evidence", "Damage Evidence", "Cost Estimate Evidence", "Public Liability
    Insurance", "Other Supporting Documents"). `order` keeps damage items in
    page order; application-level items sort last.
    """

    url: str
    filename: str
    group: str
    category: str
    order: int = 0


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of attempting to save one attachment."""

    filename: str
    url: str
    ok: bool
    size: int = 0
    error: str = ""
