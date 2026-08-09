import io
import zipfile

from pathlib import Path

from core.downloader import (
    build_zip,
    dedupe_names,
    filename_from_content_disposition,
    safe_filename,
    write_tree,
)


def test_safe_filename_strips_unsafe_chars():
    assert safe_filename('a/b\\c:d*?.pdf') == "a_b_c_d__.pdf"
    assert safe_filename("  spaced .pdf ") == "spaced .pdf"
    assert safe_filename("") == "attachment"
    assert safe_filename("...", fallback="x") == "x"


def test_safe_filename_caps_length():
    name = "x" * 300 + ".pdf"
    out = safe_filename(name)
    assert len(out) <= 180
    assert out.endswith(".pdf")


def test_filename_from_content_disposition_plain():
    assert (
        filename_from_content_disposition('attachment; filename="Report Q3.pdf"')
        == "Report Q3.pdf"
    )


def test_filename_from_content_disposition_rfc5987():
    header = "attachment; filename*=UTF-8''Report%20%C3%A9.pdf"
    assert filename_from_content_disposition(header) == "Report é.pdf"


def test_filename_from_content_disposition_missing():
    assert filename_from_content_disposition(None) is None
    assert filename_from_content_disposition("inline") is None


def test_dedupe_names():
    names = ["a.pdf", "a.pdf", "a.pdf", "b.txt"]
    assert dedupe_names(names) == ["a.pdf", "a (2).pdf", "a (3).pdf", "b.txt"]


def test_dedupe_names_case_insensitive():
    assert dedupe_names(["File.PDF", "file.pdf"]) == ["File.PDF", "file (2).pdf"]


def test_dedupe_names_no_extension():
    assert dedupe_names(["report", "report"]) == ["report", "report (2)"]


def test_build_zip_roundtrip():
    data = build_zip([("a.txt", b"hello"), ("b.txt", b"world")])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert sorted(zf.namelist()) == ["a.txt", "b.txt"]
        assert zf.read("a.txt") == b"hello"


def test_write_tree_to_disk(tmp_path):
    entries = [
        ("Damage 01/Damage Evidence", "1.jpeg", b"a"),
        ("Damage 02/Damage Evidence", "1.jpeg", b"b"),  # same name, other folder
        ("Damage 01/Damage Evidence", "1.jpeg", b"c"),  # clash within folder -> renamed
        ("Application-level/Public Liability Insurance", "cofc.pdf", b"d"),
    ]
    written = write_tree(entries, str(tmp_path))
    assert len(written) == 4

    assert (tmp_path / "Damage 01" / "Damage Evidence" / "1.jpeg").read_bytes() == b"a"
    assert (tmp_path / "Damage 02" / "Damage Evidence" / "1.jpeg").read_bytes() == b"b"
    # The within-folder clash was renamed, not overwritten.
    assert (tmp_path / "Damage 01" / "Damage Evidence" / "1 (2).jpeg").read_bytes() == b"c"
    assert (
        tmp_path / "Application-level" / "Public Liability Insurance" / "cofc.pdf"
    ).read_bytes() == b"d"
