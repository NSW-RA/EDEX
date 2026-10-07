"""Parse a SmartyGrants EPAR *Application* page and lay out the folder tree.

The Application form renders the Damage Information question as a grid
(`table.ftViewGrid`). Two facts make categorisation reliable without ever
trusting a filename:

  * Every data cell carries `headers="gridheads{grid}_q{question}"`, and the
    matching `<th id="…">` holds that column's label. So a file's **category**
    comes from the column its cell belongs to.
  * Each row is one damage item; the row's own **Damage Item ID** and **Asset
    Name** cells identify it. So a file's **damage item** comes from its row.

Non-grid uploads (Public Liability Insurance, Supporting Documentation) live in
ordinary `ftFileList` blocks outside the grid and are treated as
application-level files.

`plan()` turns a parse into the exact folder tree EDEX produces (confirmed with
the user, 2026-10-07):

    <EPAR ID>/
    └── Application/
        ├── Application Form/              (PLI + supporting docs; staff add the form)
        └── Damage Evidence/
            └── <Damage ID> - <Asset Name>/
                ├── Pre-Disaster Evidence/
                ├── Damage Evidence/
                ├── Cost Estimation Evidence/
                └── Completion/            (always empty — staff fill later)

All four damage sub-folders, plus Application Form, are always created even when
empty, so the structure is uniform.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.models import CategorisedFile, DamageItem

APPLICATION_FOLDER = "Application"
APPLICATION_FORM_FOLDER = "Application Form"
DAMAGE_WRAPPER_FOLDER = "Damage Evidence"
# The four sub-folders every damage item gets, in order. "Completion" is always
# left empty (staff add completion evidence later).
DAMAGE_SUBFOLDERS = (
    "Pre-Disaster Evidence",
    "Damage Evidence",
    "Cost Estimation Evidence",
    "Completion",
)

_APP_ORDER = 1_000_000  # application-level files sort after all damage items


@dataclass
class ApplicationParse:
    epar_id: str
    damage_items: list[DamageItem] = field(default_factory=list)
    files: list[CategorisedFile] = field(default_factory=list)


def _damage_category(label: str) -> str:
    """Map a grid column label to its damage evidence sub-folder."""
    low = " ".join((label or "").lower().split())
    if "pre-disaster" in low or "pre disaster" in low:
        return "Pre-Disaster Evidence"
    if "damage evidence" in low:
        return "Damage Evidence"
    if "cost estimat" in low:
        return "Cost Estimation Evidence"
    cleaned = re.sub(r"(?i)\bupload\b", " ", label or "").strip(" .:-")
    return " ".join(cleaned.split()) or "Evidence"


def _clean_value(td) -> str:
    """Cell text with the '* Required' marker removed."""
    txt = td.get_text(" ", strip=True).replace("*", " ")
    txt = re.sub(r"(?i)\brequired\b", " ", txt)
    return " ".join(txt.split())


def _link_name(a) -> str:
    return " ".join(a.get_text(" ", strip=True).split())


def _headers_key(td) -> str:
    """`headers` is a space-separated (multi-valued) attribute -> normalise to str."""
    value = td.get("headers")
    if isinstance(value, list):
        return " ".join(value)
    return value or ""


def damage_folder_name(item: DamageItem) -> str:
    """'<Damage ID> - <Asset Name>', or just the ID / a fallback."""
    label = item.damage_id or f"Item {item.order}"
    return f"{label} - {item.asset_name}" if item.asset_name else label


def _parse_grid(grid, base_url: str, out: ApplicationParse) -> None:
    header_label: dict[str, str] = {}
    for th in grid.select("thead th"):
        hid = th.get("id")
        if hid:
            header_label[hid] = " ".join(th.get_text(" ", strip=True).split())

    def hid_for(name: str) -> str | None:
        for hid, lab in header_label.items():
            if lab.lower() == name:
                return hid
        return None

    damage_id_hid = hid_for("damage item id")
    asset_name_hid = hid_for("asset name")

    order = 0
    for tr in grid.select("tbody > tr"):
        cells = [td for td in tr.find_all("td", recursive=False) if td.has_attr("headers")]
        if not cells:
            continue  # the first tbody row is hints (no headers= attrs)
        order += 1
        by_header = {_headers_key(td): td for td in cells}
        damage_id = _clean_value(by_header[damage_id_hid]) if damage_id_hid in by_header else ""
        asset_name = _clean_value(by_header[asset_name_hid]) if asset_name_hid in by_header else ""
        out.damage_items.append(DamageItem(order=order, damage_id=damage_id, asset_name=asset_name))

        for td in cells:
            links = td.select("ul.ftFileList li.ftFile a[href]")
            if not links:
                continue
            category = _damage_category(header_label.get(_headers_key(td), ""))
            for a in links:
                out.files.append(
                    CategorisedFile(
                        url=urljoin(base_url, a["href"]),
                        filename=_link_name(a),
                        damage_id=damage_id or f"__row{order}",
                        category=category,
                        order=order,
                    )
                )


def _parse_non_grid(soup, base_url: str, out: ApplicationParse) -> None:
    for ul in soup.select("ul.ftFileList"):
        if ul.find_parent("table", class_="ftViewGrid") is not None:
            continue  # handled by the grid parser
        for a in ul.select("li.ftFile a[href]"):
            out.files.append(
                CategorisedFile(
                    url=urljoin(base_url, a["href"]),
                    filename=_link_name(a),
                    damage_id=None,  # application-level -> Application Form
                    category="",
                    order=_APP_ORDER,
                )
            )


def _epar_id(soup) -> str:
    heading = soup.select_one("#subHeading")
    text = heading.get_text(" ", strip=True) if heading else ""
    match = re.search(r"\bEP\w+", text)
    return match.group(0) if match else ""


def parse_application(
    html: str, base_url: str = "https://manage.smartygrants.com.au"
) -> ApplicationParse:
    """Parse Application-page HTML into damage items and categorised files."""
    soup = BeautifulSoup(html, "html.parser")
    out = ApplicationParse(epar_id=_epar_id(soup))
    for grid in soup.select("table.ftViewGrid"):
        _parse_grid(grid, base_url, out)
    _parse_non_grid(soup, base_url, out)

    # De-duplicate exact (damage_id, category, url) repeats.
    seen: set[tuple] = set()
    unique: list[CategorisedFile] = []
    for f in out.files:
        key = (f.damage_id, f.category, f.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    out.files = unique
    return out


def plan(parse: ApplicationParse) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Lay out the folder tree.

    Returns (file_targets, empty_folders):
      * file_targets: (folder, filename, url) for every file to download, where
        folder is its full zip-relative path under <EPAR ID>/.
      * empty_folders: every folder that must exist even when empty — the four
        sub-folders of each damage item, and Application Form.
    """
    epar = parse.epar_id or "EDEX"
    application = f"{epar}/{APPLICATION_FOLDER}"
    app_form = f"{application}/{APPLICATION_FORM_FOLDER}"

    empty_folders: list[str] = [app_form]
    damage_base: dict[int, str] = {}
    for item in parse.damage_items:
        base = f"{application}/{DAMAGE_WRAPPER_FOLDER}/{damage_folder_name(item)}"
        damage_base[item.order] = base
        for sub in DAMAGE_SUBFOLDERS:
            empty_folders.append(f"{base}/{sub}")

    file_targets: list[tuple[str, str, str]] = []
    for f in parse.files:
        if f.damage_id is None:
            folder = app_form
        else:
            base = damage_base.get(f.order)
            folder = f"{base}/{f.category}" if base else app_form
        file_targets.append((folder, f.filename, f.url))

    return file_targets, empty_folders
