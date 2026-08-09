"""Turn a page's raw links into a de-duplicated list of Attachments.

Kept free of Playwright so it can be unit-tested: the browser worker hands us
plain (href, text) tuples plus the page URL, and this module does the URL
resolution, extension detection, and filtering.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlsplit

from core.models import Attachment

_SG_HOST = "manage.smartygrants.com.au"
# Matches a SmartyGrants application URL and captures the internal numeric id.
_SG_APP_RE = re.compile(r"smartygrants\.com\.au/application/(\d+)", re.IGNORECASE)


def normalize_target_url(raw: str, tab: str = "files") -> tuple[str, bool]:
    """Resolve user input to the page EDEX should scrape.

    For SmartyGrants we route to a chosen tab of the application:
      - "files"       -> the Files tab, the flat list of every attachment;
      - "application" -> the Application page, whose damage grid gives the
                          per-damage-item / per-category context for foldering.
    Accepts a bare application number ("4606199"), any SmartyGrants application
    URL, or anything else (returned unchanged).

    Returns (url, routed_to_smartygrants).
    """
    raw = (raw or "").strip()
    if raw.isdigit():
        return f"https://{_SG_HOST}/application/{raw}/{tab}", True
    match = _SG_APP_RE.search(raw)
    if match:
        return f"https://{_SG_HOST}/application/{match.group(1)}/{tab}", True
    return raw, False

# Extensions offered as the default filter in the UI. Not exhaustive — the UI
# lets the user add their own — but it covers the documents a grants/EM portal
# usually carries.
DEFAULT_EXTENSIONS: tuple[str, ...] = (
    "pdf", "doc", "docx", "xls", "xlsx", "csv",
    "ppt", "pptx", "zip", "txt", "rtf",
    "jpg", "jpeg", "png", "tif", "tiff", "msg", "eml",
)

# A broader set used to decide whether a link's *visible text* names a file.
# SmartyGrants (and similar portals) serve downloads from an extension-less
# endpoint like /application/1234/download/5678, while the real filename —
# "PRE_CBRS01.pdf" — is the link's text. We only trust a trailing ".xxx" in the
# text when xxx is a known file type, so a website link whose text ends in
# ".gov.au" isn't mistaken for a file.
KNOWN_FILE_EXTS: frozenset[str] = frozenset({
    "pdf", "doc", "docx", "docm", "dot", "dotx", "rtf", "txt", "odt",
    "xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "csv", "tsv", "ods",
    "ppt", "pptx", "ppsx", "odp",
    "zip", "7z", "rar", "tar", "gz",
    "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "svg", "webp", "heic",
    "msg", "eml",
    "mp4", "mov", "avi", "wmv", "mkv", "mp3", "wav",
    "kml", "kmz", "dwg", "dxf", "shp", "geojson", "json", "xml",
})

# URL fragments that mark a SmartyGrants / generic download endpoint, used as a
# fallback when neither the URL nor the link text carries a file extension.
_DOWNLOAD_HINTS: tuple[str, ...] = ("/download", "/files/", "submissionfile", "/attachment")


def filename_from_url(url: str) -> str:
    """Last path segment of a URL, percent-decoded. '' when the path is empty."""
    path = urlsplit(url).path
    last = path.rsplit("/", 1)[-1] if path else ""
    return unquote(last)


def ext_of(name: str) -> str:
    """Lower-case extension without the dot, or '' if the name has none."""
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def build_attachments(links: list[tuple[str, str]], page_url: str) -> list[Attachment]:
    """Resolve, de-duplicate, and describe the links found on a page.

    `links` is a list of (href, visible_text) as read from the DOM. Fragment-only
    and javascript:/mailto: hrefs are dropped. Order of first appearance is kept
    so the list the user sees matches the page.
    """
    # The DOM resolves hrefs to absolute for us, so a same-page "#section"
    # anchor arrives as "<page_url>#section". Drop anything that points back at
    # the page itself (once the fragment is removed) alongside non-file schemes.
    page_key = page_url.split("#", 1)[0]

    seen: set[str] = set()
    out: list[Attachment] = []
    for href, text in links:
        href = (href or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        # Ignore the fragment when de-duplicating; two anchors to the same file
        # with different #hash are the same download.
        key = absolute.split("#", 1)[0]
        if key in seen or key == page_key:
            continue
        seen.add(key)
        out.append(_describe(key, (text or "").strip()))
    return out


def _describe(url: str, text: str) -> Attachment:
    """Work out an attachment's filename, extension, and whether it is a file.

    Detection order, most reliable first:
      1. The URL path ends in an extension (a plain file link).
      2. The link text ends in a *known* file extension (portals that serve
         downloads from an extension-less endpoint but label the link with the
         real filename — this is how SmartyGrants presents uploads).
      3. The URL looks like a download endpoint (/download, /files/, ...); we
         keep it as a file but leave the extension blank until download time,
         when Content-Disposition supplies the real name.
    """
    url_name = filename_from_url(url)
    url_ext = ext_of(url_name)
    if url_ext:
        return Attachment(url=url, text=text, filename=url_name, ext=url_ext, is_file=True)

    text_ext = ext_of(text)
    if text_ext and text_ext in KNOWN_FILE_EXTS:
        return Attachment(url=url, text=text, filename=text, ext=text_ext, is_file=True)

    if any(hint in url.lower() for hint in _DOWNLOAD_HINTS):
        return Attachment(url=url, text=text, filename=(text or url_name), ext="", is_file=True)

    # Plain navigation / external link — kept, but not treated as an attachment.
    return Attachment(url=url, text=text, filename=url_name, ext="", is_file=False)


def only_files(attachments: list[Attachment]) -> list[Attachment]:
    """Keep just the links that look like real attachments (drop navigation)."""
    return [a for a in attachments if a.is_file]


def filter_by_extension(
    attachments: list[Attachment], extensions: list[str]
) -> list[Attachment]:
    """Keep only attachments whose extension is in `extensions` (case-insensitive).

    An empty `extensions` list means 'no filter' — everything is returned, which
    is how the UI exposes 'include links without a file extension' (e.g. portal
    download endpoints like /download?id=123).
    """
    if not extensions:
        return list(attachments)
    wanted = {e.lower().lstrip(".") for e in extensions}
    return [a for a in attachments if a.ext in wanted]
