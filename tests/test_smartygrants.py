import io
import zipfile
from pathlib import Path

from core.downloader import build_tree_zip
from core.smartygrants import categorise_label, parse_application

FIXTURE = (Path(__file__).parent / "fixtures" / "epar_application.html").read_text(encoding="utf-8")


def _parse():
    return parse_application(FIXTURE)


def test_categorise_label():
    assert categorise_label("Pre-Disaster Evidence Upload") == "Pre-Disaster Evidence"
    assert categorise_label("Damage Evidence Upload") == "Damage Evidence"
    assert categorise_label("Upload Cost Estimation Evidence") == "Cost Estimate Evidence"
    assert (
        categorise_label("Please provide evidence that the applicant organisation holds Public Liability Insurance.")
        == "Public Liability Insurance"
    )
    assert categorise_label("Supporting Documentation") == "Other Supporting Documents"


def test_epar_id_extracted():
    assert _parse().epar_id == "EP11700000005"


def test_grid_files_get_row_and_column():
    files = _parse().files
    # Look up by url tail for stability.
    by_tail = {f.url.rsplit("/", 1)[-1]: f for f in files}

    pre1 = by_tail["f4198"]
    assert pre1.filename == "PRE_CBRS01.pdf"
    assert pre1.group == "Damage 01 — CBRS1 (Carrowbrook Road)"
    assert pre1.category == "Pre-Disaster Evidence"

    cost1b = by_tail["cost01b"]
    assert cost1b.filename == "CBRS01 - Estimate Submission.xlsx"
    assert cost1b.group == "Damage 01 — CBRS1 (Carrowbrook Road)"
    assert cost1b.category == "Cost Estimate Evidence"


def test_generic_filename_disambiguated_by_row():
    # Both damage rows have a Damage Evidence file literally named "1.jpeg".
    files = _parse().files
    jpegs = [f for f in files if f.filename == "1.jpeg"]
    assert len(jpegs) == 2
    groups = {f.group for f in jpegs}
    assert groups == {
        "Damage 01 — CBRS1 (Carrowbrook Road)",
        "Damage 02 — CBRS2 (Carrowbrook Road)",
    }
    assert all(f.category == "Damage Evidence" for f in jpegs)


def test_non_grid_uploads_are_application_level():
    files = _parse().files
    by_name = {f.filename: f for f in files}

    pil = by_name["SINGLE 2025-26 PIL Generic CofC.pdf"]
    assert pil.group == "Application-level"
    assert pil.category == "Public Liability Insurance"

    sup = by_name["Council resolution.pdf"]
    assert sup.group == "Application-level"
    assert sup.category == "Other Supporting Documents"


def test_download_dropdown_is_ignored():
    # The dropdown lists PRE_CBRS01.pdf/DMG_CBRS01.pdf with #-style hrefs; the
    # parser must only pick up the in-context ftFileList links, so each real
    # file appears exactly once and none point at the dropdown's dummy hashes.
    files = _parse().files
    assert sum(f.filename == "PRE_CBRS01.pdf" for f in files) == 1
    assert not any(f.url.endswith(("/aaaa", "/bbbb")) for f in files)


def test_tree_zip_layout_keeps_same_name_apart():
    files = _parse().files
    entries = [(f"{f.group}/{f.category}", f.filename, b"x") for f in files]
    data = build_tree_zip(entries)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())

    assert "Damage 01 — CBRS1 (Carrowbrook Road)/Pre-Disaster Evidence/PRE_CBRS01.pdf" in names
    assert "Damage 01 — CBRS1 (Carrowbrook Road)/Damage Evidence/1.jpeg" in names
    assert "Damage 02 — CBRS2 (Carrowbrook Road)/Damage Evidence/1.jpeg" in names
    assert "Application-level/Public Liability Insurance/SINGLE 2025-26 PIL Generic CofC.pdf" in names
    # Two same-named files survive because they're in different folders.
    assert sum(n.endswith("/Damage Evidence/1.jpeg") for n in names) == 2
