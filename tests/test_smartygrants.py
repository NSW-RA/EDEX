import io
import zipfile
from pathlib import Path

from core.downloader import build_tree_zip
from core.smartygrants import damage_folder_name, parse_application, plan

FIXTURE = (Path(__file__).parent / "fixtures" / "epar_application.html").read_text(encoding="utf-8")


def _parse():
    return parse_application(FIXTURE)


def test_epar_id_and_damage_items():
    p = _parse()
    assert p.epar_id == "EP11700000005"
    items = {(d.order, d.damage_id, d.asset_name) for d in p.damage_items}
    assert items == {
        (1, "CBRS1", "Carrowbrook Road"),
        (2, "CBRS2", "Carrowbrook Road"),
    }


def test_damage_folder_name():
    p = _parse()
    names = sorted(damage_folder_name(d) for d in p.damage_items)
    assert names == ["CBRS1 - Carrowbrook Road", "CBRS2 - Carrowbrook Road"]


def test_files_get_damage_id_and_category():
    by_tail = {f.url.rsplit("/", 1)[-1]: f for f in _parse().files}
    pre1 = by_tail["f4198"]
    assert pre1.filename == "PRE_CBRS01.pdf"
    assert pre1.damage_id == "CBRS1"
    assert pre1.category == "Pre-Disaster Evidence"

    cost1b = by_tail["cost01b"]
    assert cost1b.category == "Cost Estimation Evidence"
    assert cost1b.damage_id == "CBRS1"


def test_generic_filename_disambiguated_by_row():
    jpegs = [f for f in _parse().files if f.filename == "1.jpeg"]
    assert len(jpegs) == 2
    assert {f.damage_id for f in jpegs} == {"CBRS1", "CBRS2"}
    assert all(f.category == "Damage Evidence" for f in jpegs)


def test_non_grid_files_are_application_level():
    app = {f.filename for f in _parse().files if f.damage_id is None}
    assert "SINGLE 2025-26 PIL Generic CofC.pdf" in app
    assert "Council resolution.pdf" in app


def test_download_dropdown_is_ignored():
    files = _parse().files
    assert sum(f.filename == "PRE_CBRS01.pdf" for f in files) == 1
    assert not any(f.url.endswith(("/aaaa", "/bbbb")) for f in files)


def test_plan_targets_and_empty_folders():
    targets, empty = plan(_parse())
    by_name = {name: folder for folder, name, _url in targets}

    assert by_name["PRE_CBRS01.pdf"] == (
        "EP11700000005/Application/Damage Evidence/CBRS1 - Carrowbrook Road/Pre-Disaster Evidence"
    )
    assert by_name["CBRS01 - Estimate Submission.xlsx"].endswith(
        "CBRS1 - Carrowbrook Road/Cost Estimation Evidence"
    )
    # Application-level files land in Application Form.
    assert by_name["SINGLE 2025-26 PIL Generic CofC.pdf"] == (
        "EP11700000005/Application/Application Form"
    )

    # Every damage item has all four sub-folders in empty_folders, plus App Form.
    assert "EP11700000005/Application/Application Form" in empty
    for did in ("CBRS1 - Carrowbrook Road", "CBRS2 - Carrowbrook Road"):
        for sub in ("Pre-Disaster Evidence", "Damage Evidence", "Cost Estimation Evidence", "Completion"):
            assert f"EP11700000005/Application/Damage Evidence/{did}/{sub}" in empty


def test_zip_has_empty_completion_and_splits_duplicates():
    targets, empty = plan(_parse())
    entries = [(folder, name, b"x") for folder, name, _url in targets]
    data = build_tree_zip(entries, empty_folders=empty)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())

    # Empty Completion folders exist as directory entries.
    assert "EP11700000005/Application/Damage Evidence/CBRS1 - Carrowbrook Road/Completion/" in names
    assert "EP11700000005/Application/Damage Evidence/CBRS2 - Carrowbrook Road/Completion/" in names

    # The two 1.jpeg files survive in their own damage folders.
    assert sum(n.endswith("/Damage Evidence/1.jpeg") for n in names) == 2
    base = "EP11700000005/Application/Damage Evidence"
    assert f"{base}/CBRS1 - Carrowbrook Road/Damage Evidence/1.jpeg" in names
    assert f"{base}/CBRS2 - Carrowbrook Road/Damage Evidence/1.jpeg" in names

    # Application-level file placed in Application Form.
    assert (
        "EP11700000005/Application/Application Form/SINGLE 2025-26 PIL Generic CofC.pdf" in names
    )
