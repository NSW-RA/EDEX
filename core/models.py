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
class DamageItem:
    """One damage line item (row) in the Application damage grid.

    `order` is the row's position (1-based). `damage_id` is its Damage Item ID
    (e.g. "CBRS1"); `asset_name` is the Asset Name (e.g. "Carrowbrook Road").
    """

    order: int
    damage_id: str
    asset_name: str


@dataclass(frozen=True)
class CategorisedFile:
    """An attachment and where it belongs in the EPAR folder tree.

    `damage_id` is the Damage Item ID the file belongs to, or None for an
    application-level file (which goes in the "Application Form" folder).
    `category` is the evidence sub-folder for a damage file ("Pre-Disaster
    Evidence", "Damage Evidence", "Cost Estimation Evidence"); it is "" for an
    application-level file. `order` is the owning damage item's row order
    (application-level files sort last).
    """

    url: str
    filename: str
    damage_id: str | None
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
