from core.scraper import (
    build_attachments,
    ext_of,
    filename_from_url,
    filter_by_extension,
    normalize_target_url,
    only_files,
)


def test_normalize_target_url_from_number():
    url, routed = normalize_target_url("4606199")
    assert routed is True
    assert url == "https://manage.smartygrants.com.au/application/4606199/files"


def test_normalize_target_url_from_application_url():
    url, routed = normalize_target_url(
        "https://manage.smartygrants.com.au/application/4606199/application"
    )
    assert routed is True
    assert url.endswith("/application/4606199/files")


def test_normalize_target_url_files_url_is_idempotent():
    src = "https://manage.smartygrants.com.au/application/4606199/files"
    url, routed = normalize_target_url(src)
    assert routed is True
    assert url == src


def test_normalize_target_url_passthrough_for_other_sites():
    src = "https://portal.example.nsw.gov.au/case/12345"
    url, routed = normalize_target_url(src)
    assert routed is False
    assert url == src

PAGE = "https://portal.example.nsw.gov.au/case/12345"


def test_filename_from_url_decodes_percent_encoding():
    assert filename_from_url("https://x/y/My%20Report.pdf") == "My Report.pdf"
    assert filename_from_url("https://x/download?id=7") == "download"
    assert filename_from_url("https://x/") == ""


def test_ext_of():
    assert ext_of("report.PDF") == "pdf"
    assert ext_of("archive.tar.gz") == "gz"
    assert ext_of("noext") == ""


def test_build_attachments_resolves_and_dedupes():
    links = [
        ("https://portal.example.nsw.gov.au/files/a.pdf", "Report A"),
        ("https://portal.example.nsw.gov.au/files/a.pdf#page=2", "Report A again"),
        ("https://portal.example.nsw.gov.au/files/b.docx", "Doc B"),
    ]
    out = build_attachments(links, PAGE)
    # a.pdf appears twice (differing only by fragment) -> one entry.
    assert [a.filename for a in out] == ["a.pdf", "b.docx"]
    assert out[0].ext == "pdf"
    assert out[0].url == "https://portal.example.nsw.gov.au/files/a.pdf"


def test_build_attachments_drops_self_and_fragment_links():
    # The DOM hands us absolute hrefs, so a "#top" anchor arrives as the page
    # URL plus a fragment. It must not become an "attachment".
    links = [
        (PAGE + "#top", "Back to top"),
        (PAGE, "Reload"),
        (PAGE + "/files/real.pdf", "Real"),
    ]
    out = build_attachments(links, PAGE)
    assert [a.url for a in out] == [PAGE + "/files/real.pdf"]


def test_build_attachments_skips_non_file_schemes():
    links = [
        ("mailto:someone@example.com", "Email"),
        ("javascript:void(0)", "JS"),
        ("#top", "Anchor"),
        ("tel:+61290000000", "Phone"),
        ("/files/real.xlsx", "Real"),
    ]
    out = build_attachments(links, PAGE)
    assert len(out) == 1
    assert out[0].url == "https://portal.example.nsw.gov.au/files/real.xlsx"


def test_smartygrants_style_endpoint_link():
    # SmartyGrants: the href is an extension-less download endpoint, the real
    # filename is the link text. Must be detected as a pdf attachment.
    links = [
        ("https://manage.smartygrants.com.au/application/4606199/download/5678",
         "PRE_CBRS01.pdf"),
    ]
    out = build_attachments(links, "https://manage.smartygrants.com.au/application/4606199/application")
    assert len(out) == 1
    a = out[0]
    assert a.is_file is True
    assert a.filename == "PRE_CBRS01.pdf"
    assert a.ext == "pdf"


def test_website_link_text_is_not_a_file():
    # A link whose text ends in ".gov.au" must NOT be mistaken for a file.
    links = [("https://www.singleton.nsw.gov.au", "https://www.singleton.nsw.gov.au")]
    out = build_attachments(links, PAGE)
    assert out[0].is_file is False
    assert out[0].ext == ""


def test_download_endpoint_without_extension_is_file():
    links = [("https://portal/app/1/download/9", "Download evidence")]
    out = build_attachments(links, PAGE)
    assert out[0].is_file is True
    assert out[0].ext == ""
    assert out[0].filename == "Download evidence"


def test_only_files_drops_navigation():
    links = [
        ("/a.pdf", "a"),
        ("/help", "Help"),
        ("https://manage.smartygrants.com.au/application/1/download/2", "b.docx"),
        ("/show-map", "Show map"),
    ]
    out = build_attachments(links, PAGE)
    files = only_files(out)
    assert {f.filename for f in files} == {"a.pdf", "b.docx"}


def test_filter_by_extension():
    links = [
        ("/a.pdf", "a"),
        ("/b.docx", "b"),
        ("/c.png", "c"),
        ("/download?id=9", "d"),  # no extension
    ]
    out = build_attachments(links, PAGE)
    pdfs = filter_by_extension(out, ["pdf"])
    assert [a.filename for a in pdfs] == ["a.pdf"]
    # Empty filter = keep everything (including the extension-less endpoint).
    assert len(filter_by_extension(out, [])) == 4
    # Case-insensitive and dot-tolerant.
    assert len(filter_by_extension(out, [".PDF", "DOCX"])) == 2
