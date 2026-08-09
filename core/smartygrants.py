"""Parse a SmartyGrants EPAR *Application* page into categorised attachments.

The Application form renders the Damage Information question as a grid
(`table.ftViewGrid`). Two facts make categorisation reliable without ever
trusting a filename:

  * Every data cell carries `headers="gridheads{grid}_q{question}"`, and the
    matching `<th id="…">` holds that column's label. So a file's **category**
    comes from the column its cell belongs to.
  * Each row is one damage item; the row's own **Damage Item ID** and **Asset
    Name** cells identify it. So a file's **damage item** comes from its row.

Two files both named "1.jpeg" in different rows therefore land in different
damage folders — the row, not the name, separates them.

Non-grid uploads (Public Liability Insurance, Supporting Documentation) live in
ordinary `ftViewQuestion` blocks and are grouped under "Application-level", with
the category taken from the question label.

The form's "Download" dropdown lists every file flatly with no context; it is
NOT an `ftFileList`, so restricting to `ul.ftFileList` ignores it cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.models import CategorisedFile

APPLICATION_GROUP = "Application-level"
_APP_ORDER = 1_000_000  # sorts application-level groups after all damage items


@dataclass
class ApplicationParse:
    epar_id: str
    files: list[CategorisedFile] = field(default_factory=list)


def categorise_label(label: str) -> str:
    """Map a column/question label to one of the agreed category folders."""
    low = " ".join((label or "").lower().split())
    if "pre-disaster" in low or "pre disaster" in low:
        return "Pre-Disaster Evidence"
    if "damage evidence" in low:
        return "Damage Evidence"
    if "cost estimat" in low:
        return "Cost Estimate Evidence"
    if "public liability" in low or "liability insurance" in low:
        return "Public Liability Insurance"
    if "supporting" in low:
        return "Other Supporting Documents"
    # Fallback: strip a leading/trailing "Upload" and tidy up.
    cleaned = re.sub(r"(?i)\bupload\b", " ", label or "").strip(" .:-")
    cleaned = " ".join(cleaned.split())
    return cleaned or "Other Supporting Documents"


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


def _damage_group(order: int, damage_id: str, asset_name: str) -> str:
    label = damage_id or f"Item {order}"
    base = f"Damage {order:02d} — {label}"
    return f"{base} ({asset_name})" if asset_name else base


def _parse_grid(grid, base_url: str, out: list[CategorisedFile]) -> None:
    # header id -> label, and label(lower) -> header id for the identity columns.
    header_label: dict[str, str] = {}
    for th in grid.select("thead th"):
        hid = th.get("id")
        if not hid:
            continue
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
        group = _damage_group(order, damage_id, asset_name)

        for td in cells:
            links = td.select("ul.ftFileList li.ftFile a[href]")
            if not links:
                continue
            category = categorise_label(header_label.get(_headers_key(td), ""))
            for a in links:
                out.append(
                    CategorisedFile(
                        url=urljoin(base_url, a["href"]),
                        filename=_link_name(a),
                        group=group,
                        category=category,
                        order=order,
                    )
                )


def _question_label(ul) -> str:
    """Climb to the enclosing ftViewQuestion that carries a label, return it."""
    node = ul
    while node is not None:
        question = node.find_parent(class_="ftViewQuestion")
        if question is None:
            return ""
        label = question.find("label", class_="ftViewLabel")
        if label:
            span = label.find("span", id=lambda x: bool(x) and x.endswith("_questionText"))
            return " ".join((span or label).get_text(" ", strip=True).split())
        node = question
    return ""


def _parse_non_grid(soup, base_url: str, out: list[CategorisedFile]) -> None:
    for ul in soup.select("ul.ftFileList"):
        if ul.find_parent("table", class_="ftViewGrid") is not None:
            continue  # handled by the grid parser
        category = categorise_label(_question_label(ul))
        for a in ul.select("li.ftFile a[href]"):
            out.append(
                CategorisedFile(
                    url=urljoin(base_url, a["href"]),
                    filename=_link_name(a),
                    group=APPLICATION_GROUP,
                    category=category,
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
    """Parse Application-page HTML into a de-duplicated list of CategorisedFiles."""
    soup = BeautifulSoup(html, "html.parser")
    files: list[CategorisedFile] = []
    for grid in soup.select("table.ftViewGrid"):
        _parse_grid(grid, base_url, files)
    _parse_non_grid(soup, base_url, files)

    seen: set[tuple[str, str, str]] = set()
    unique: list[CategorisedFile] = []
    for f in files:
        key = (f.group, f.category, f.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return ApplicationParse(epar_id=_epar_id(soup), files=unique)
