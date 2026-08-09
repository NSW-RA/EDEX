"""Results page: review discovered attachments, then download them.

Two modes, set on the main page:
  * "categorised" — SmartyGrants EPAR files sorted into a Damage-item / evidence
    folder tree and delivered as one structured zip.
  * "flat" — a single reviewable list of links, bundled into a flat zip.

Downloads reuse the signed-in browser session (core.browser), so files behind
the login come through with the right cookies.
"""

import logging
from collections import OrderedDict
from html import escape
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="EDEX — Results", layout="wide")

st.html(
    """
    <style>
        .stMainBlockContainer {
            max-width: 100% !important;
            padding-top: 2rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            box-sizing: border-box !important;
        }
    </style>
    """
)

from core.browser import BrowserError
from core.downloader import (
    build_tree_zip,
    build_zip,
    dedupe_names,
    filename_from_content_disposition,
    safe_filename,
    write_tree,
)
from core.scraper import filter_by_extension, only_files
from core.smartygrants import APPLICATION_GROUP
from utils.session import get_session
from utils.ui import (
    render_empty_state,
    render_footer,
    render_header,
    render_nosection,
    render_summary,
)

logger = logging.getLogger(__name__)

render_header("EDEX — Results")
render_nosection()

scrape = st.session_state.get("scrape")


def _back_and_stop(message: str) -> None:
    render_empty_state("Nothing to show yet", message)
    if st.button("← Back to start", type="secondary"):
        st.switch_page("app.py")
    render_nosection()
    render_footer()
    st.stop()


if not scrape:
    _back_and_stop("Go back, sign in, and fetch an application to see its files here.")

mode = scrape.get("mode", "flat")


def _fetch_one(session, url, fallback_name, index):
    """Fetch one file; return (ok, name, data, size, error)."""
    try:
        resp = session.fetch(url)
    except BrowserError as exc:
        return (False, fallback_name, b"", 0, str(exc))
    if resp["status"] >= 400 or not resp["body"]:
        return (False, fallback_name, b"", 0, f"HTTP {resp['status']}")
    name = (
        filename_from_content_disposition(resp["content_disposition"])
        or fallback_name
        or f"attachment_{index}"
    )
    return (True, safe_filename(name, f"attachment_{index}"), resp["body"], len(resp["body"]), "")


def _result_row(ok: bool, label: str, size: int = 0, error: str = "") -> None:
    if ok:
        kb = f"{size / 1024:.0f} KB" if size < 1_048_576 else f"{size / 1_048_576:.1f} MB"
        st.markdown(
            f'<div class="edex-result edex-result--ok">✓ {escape(label)} <span>({kb})</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="edex-result edex-result--fail">✕ {escape(label)} — {escape(error)}</div>',
            unsafe_allow_html=True,
        )


# =====================================================================
# Categorised (SmartyGrants EPAR) mode
# =====================================================================
if mode == "categorised":
    files = scrape.get("files") or []
    epar_id = scrape.get("epar_id") or "EDEX"
    page_url = scrape.get("page_url", "")

    if not files:
        _back_and_stop(
            "No uploaded files were found on the Application page. If you expected "
            "some, try again with folder-sorting off to see the flat list."
        )

    # Group -> category -> [files], preserving damage-item / category order.
    ordered = sorted(files, key=lambda f: (f.order, f.group, f.category, f.filename.lower()))
    tree: "OrderedDict[str, OrderedDict[str, list]]" = OrderedDict()
    for f in ordered:
        tree.setdefault(f.group, OrderedDict()).setdefault(f.category, []).append(f)

    damage_groups = [g for g in tree if g != APPLICATION_GROUP]
    render_summary(len(files), page_url)
    st.caption(
        f"**{len(files)}** file(s) across **{len(damage_groups)}** damage item(s)"
        + (" plus application-level documents." if APPLICATION_GROUP in tree else ".")
        + " They'll download as a zip laid out in these folders:"
    )

    for group, categories in tree.items():
        count = sum(len(v) for v in categories.values())
        with st.expander(f"📁 {group}  ·  {count} file(s)", expanded=False):
            for category, cat_files in categories.items():
                st.markdown(f"**{escape(category)}**")
                for f in cat_files:
                    st.markdown(
                        f'<div class="edex-file"><span class="edex-file__ext">'
                        f'{escape((f.filename.rsplit(".",1)[-1] if "." in f.filename else "?").upper())}'
                        f'</span><span class="edex-file__name">{escape(f.filename)}</span></div>',
                        unsafe_allow_html=True,
                    )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("← Back", type="secondary", use_container_width=True):
            st.switch_page("app.py")
    with col_b:
        start = st.button(
            f"Download all {len(files)} file(s) as folders",
            type="primary",
            use_container_width=True,
        )

    if start:
        session = get_session()
        if not session.alive:
            st.error(
                "The browser session has closed. Go back, sign in again, then re-fetch.",
                icon=":material/error:",
            )
        else:
            entries: list[tuple[str, str, bytes]] = []
            results: list[tuple[bool, str, str]] = []
            progress = st.progress(0.0, text="Starting download...")
            for i, f in enumerate(ordered, start=1):
                progress.progress(i / len(ordered), text=f"Downloading {f.filename}")
                ok, name, data, size, error = _fetch_one(session, f.url, f.filename, i)
                shown = f"{f.group} / {f.category} / {f.filename}"
                if ok:
                    entries.append((f"{f.group}/{f.category}", name, data))
                    results.append((True, f"{shown} ({size} bytes)", ""))
                else:
                    results.append((False, shown, error))
            progress.empty()

            st.session_state["download_tree"] = {
                "entries": entries,
                "zip": build_tree_zip(entries) if entries else b"",
                "results": results,
                "epar_id": epar_id,
                "count": len(entries),
            }

    download = st.session_state.get("download_tree")
    if download:
        ok_rows = [r for r in download["results"] if r[0]]
        bad_rows = [r for r in download["results"] if not r[0]]
        render_nosection()
        st.subheader(
            f"Downloaded {len(ok_rows)} of {len(download['results'])} file(s)", anchor=False
        )

        # Option A — a single zip laid out as folders.
        if download["zip"]:
            st.download_button(
                "Save as a zip",
                data=download["zip"],
                file_name=f"{safe_filename(download['epar_id'], 'EDEX')}-attachments.zip",
                mime="application/zip",
                type="secondary",
            )

        # Option B — write the folder tree straight to a folder on this machine.
        if download["entries"]:
            st.markdown("**Or save the folders straight to a location on this PC:**")
            default_dest = str(
                Path.home() / "Downloads" / f"{safe_filename(download['epar_id'], 'EDEX')}-EPAR"
            )
            dest = st.text_input(
                "Destination folder",
                value=st.session_state.get("edex_dest", default_dest),
                help="EDEX runs on your machine, so it can create these folders here directly. "
                "The folder is created if it doesn't exist.",
            )
            if st.button("Save to this folder", type="primary"):
                st.session_state["edex_dest"] = dest
                try:
                    written = write_tree(download["entries"], dest)
                    st.success(
                        f"Saved {len(written)} file(s) into folders under:\n\n`{dest}`",
                        icon=":material/check_circle:",
                    )
                except OSError as exc:
                    st.error(f"Couldn't write to that folder: {exc}", icon=":material/error:")

        render_nosection()
        for _ok, label, _err in ok_rows:
            _result_row(True, label)
        for _ok, label, err in bad_rows:
            _result_row(False, label, error=err)

    render_nosection()
    render_footer()
    st.stop()


# =====================================================================
# Flat mode
# =====================================================================
if not scrape.get("attachments"):
    _back_and_stop("Go back, sign in, and fetch a page to see its attachments here.")

attachments = scrape["attachments"]
page_url = scrape["page_url"]
extensions = scrape.get("extensions", [])

files = only_files(attachments)
nav_count = len(attachments) - len(files)

render_summary(len(files), page_url)

show_all = False
if nav_count:
    show_all = st.toggle(
        f"Show all {len(attachments)} links (including {nav_count} navigation / other links)",
        value=False,
        help="By default only links that look like real attachments are shown. "
        "Turn this on if a file you expected is missing.",
    )

displayed = attachments if show_all else files

if not displayed:
    render_empty_state(
        "No attachments detected",
        "EDEX didn't find any file links on this page. Turn on 'Show all links' to "
        "see every link, or check you fetched the right page (try the Files tab).",
    )
    if st.button("← Back", type="secondary"):
        st.switch_page("app.py")
    render_nosection()
    render_footer()
    st.stop()

# Which extensions to pre-tick. filter_by_extension with [] means "all".
preselected = set(a.url for a in filter_by_extension(displayed, extensions))

st.caption(
    "Tick the files you want, then download them as a single zip. "
    "Files matching your chosen types are ticked for you."
)

rows = [
    {
        "Download": a.url in preselected,
        "File": a.filename or a.text or a.url,
        "Type": (a.ext.upper() if a.ext else "—"),
        "Address": a.url,
    }
    for a in displayed
]

edited = st.data_editor(
    rows,
    key="attachment_table",
    hide_index=True,
    use_container_width=True,
    disabled=["File", "Type", "Address"],
    column_config={
        "Download": st.column_config.CheckboxColumn("Get", width="small"),
        "File": st.column_config.TextColumn("File", width="large"),
        "Type": st.column_config.TextColumn("Type", width="small"),
        "Address": st.column_config.TextColumn("Address", width="large"),
    },
)

selected = [a for a, row in zip(displayed, edited) if row["Download"]]

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("← Back", type="secondary", use_container_width=True):
        st.switch_page("app.py")
with col_b:
    start = st.button(
        f"Download {len(selected)} selected file(s)",
        type="primary",
        disabled=not selected,
        use_container_width=True,
    )

if start and selected:
    session = get_session()
    if not session.alive:
        st.error(
            "The browser session has closed. Go back, sign in again, then re-fetch.",
            icon=":material/error:",
        )
    else:
        results = []
        fetched: list[tuple[str, bytes]] = []
        progress = st.progress(0.0, text="Starting download...")
        for i, att in enumerate(selected, start=1):
            label = att.filename or att.text or att.url
            progress.progress(i / len(selected), text=f"Downloading {label}")
            ok, name, data, size, error = _fetch_one(session, att.url, att.filename, i)
            if ok:
                fetched.append((name, data))
                results.append((label, att.url, True, size, ""))
            else:
                results.append((label, att.url, False, 0, error))
        progress.empty()

        names = dedupe_names([name for name, _ in fetched])
        fetched = [(new, data) for new, (_, data) in zip(names, fetched)]

        st.session_state["download"] = {
            "results": results,
            "zip": build_zip(fetched) if fetched else b"",
            "count": len(fetched),
        }

download = st.session_state.get("download")
if download:
    ok = [r for r in download["results"] if r[2]]
    bad = [r for r in download["results"] if not r[2]]

    render_nosection()
    st.subheader(f"Downloaded {len(ok)} of {len(download['results'])} file(s)", anchor=False)

    if download["zip"]:
        st.download_button(
            "Save all as a zip",
            data=download["zip"],
            file_name="edex-attachments.zip",
            mime="application/zip",
            type="primary",
        )

    for label, _url, _ok, size, _err in ok:
        _result_row(True, label, size=size)
    for label, _url, _ok, _size, err in bad:
        _result_row(False, label, error=err)

render_nosection()
render_footer()
