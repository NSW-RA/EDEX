"""EDEX — SmartyGrants EPAR attachment downloader (the app).

Authenticates with the user's SmartyGrants sign-in (read from their browser, or
pasted) and fetches attachments over plain HTTP — no browser automation, so it
works on locked-down machines where automation is blocked, and it deploys to
Streamlit Community Cloud unchanged. Reuses the damage-grid parser
(core.smartygrants) and the folder-tree zip builder (core.downloader).

Run locally with run_edex.bat, or deploy this file on Streamlit Cloud.
"""

import logging

import streamlit as st

st.set_page_config(page_title="EDEX — Attachment Downloader", layout="wide")

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

from core.downloader import (
    build_tree_zip,
    build_zip,
    dedupe_names,
    filename_from_content_disposition,
    safe_filename,
)
from core.http_client import HttpClient, HttpError, cookies_from_local_browser
from core.scraper import (
    DEFAULT_EXTENSIONS,
    build_attachments,
    filter_by_extension,
    normalize_target_url,
    only_files,
)
from core.smartygrants import APPLICATION_GROUP, parse_application
from utils.ui import (
    render_footer,
    render_header,
    render_intro,
    render_nosection,
    render_splash,
)

logger = logging.getLogger(__name__)

render_splash()
render_header("EDEX — Attachment Downloader")
render_intro()
render_nosection()

st.header("Find attachments on an application", anchor=False)

url = st.text_input(
    "SmartyGrants application number or page address",
    placeholder="4606199   or   https://manage.smartygrants.com.au/application/4606199/files",
)
_, is_sg = normalize_target_url(url)

with st.expander("① Your SmartyGrants sign-in", expanded=True):
    st.markdown(
        "EDEX fetches the files **as you**, so it needs your current sign-in. "
        "Make sure you're **logged into SmartyGrants in your browser**, then let "
        "EDEX read it automatically:"
    )
    if st.button("Read my sign-in from my browser"):
        with st.spinner("Reading your browser sign-in..."):
            got = cookies_from_local_browser()
        if got:
            st.session_state["cookie_val"] = got
            st.success("Got it — your sign-in was read from your browser.", icon=":material/check_circle:")
        else:
            st.warning(
                "Couldn't read it automatically (some browsers block this). Paste it "
                "manually instead — see the steps below.",
                icon=":material/warning:",
            )
    with st.popover("Paste it manually instead"):
        st.markdown(
            "1. In your browser on a **logged-in SmartyGrants** tab, press **F12** → "
            "**Network** tab → **refresh**.\n"
            "2. Click the **first row**, find **Request Headers → `cookie`**, right-click "
            "→ **Copy value**, and paste below."
        )
    cookie = st.text_area(
        "Your sign-in (read automatically above, or pasted)",
        key="cookie_val",
        height=80,
        placeholder="SESSION=…; other=…",
    )

categorise = st.toggle(
    "Sort into folders by damage item & evidence type (SmartyGrants EPAR)",
    value=True,
    disabled=not is_sg,
    help="Reads the application's damage grid and organises the download into "
    "Damage 01 / Pre-Disaster, Damage, Cost Estimate Evidence, plus an "
    "Application-level folder. Turn off for a single flat list.",
)

extensions = st.multiselect(
    "File types to look for (flat mode only)",
    options=list(DEFAULT_EXTENSIONS),
    default=["pdf", "docx", "xlsx", "xls", "csv", "zip", "jpg", "jpeg", "png"],
)

want_categorised = categorise and is_sg

if st.button("Fetch attachments", type="primary"):
    target, _ = normalize_target_url(url, tab="application" if want_categorised else "files")
    if not target:
        st.error("Enter an application number or page address first.", icon=":material/error:")
    elif not cookie.strip():
        st.error("Paste your SmartyGrants cookie first (step ①).", icon=":material/error:")
    else:
        client = HttpClient(cookie)
        try:
            if want_categorised:
                with st.spinner("Reading the damage grid and sorting files..."):
                    result = client.scrape(target, want_html=True)
                    parsed = parse_application(result.get("html", ""), result["page_url"])
                st.session_state["cloud"] = {
                    "mode": "categorised",
                    "cookie": cookie,
                    "files": parsed.files,
                    "epar_id": parsed.epar_id,
                    "page_url": result["page_url"],
                }
            else:
                with st.spinner("Reading the page for attachments..."):
                    result = client.scrape(target)
                st.session_state["cloud"] = {
                    "mode": "flat",
                    "cookie": cookie,
                    "attachments": build_attachments(result["links"], result["page_url"]),
                    "extensions": extensions,
                    "page_url": result["page_url"],
                }
            st.session_state.pop("cloud_zip", None)
        except HttpError as exc:
            st.error(str(exc), icon=":material/error:")

state = st.session_state.get("cloud")


def _download_all(files, fallback_group=None):
    """Fetch every (folder, filename, url) and return (entries, results)."""
    client = HttpClient(state["cookie"])
    entries, results = [], []
    progress = st.progress(0.0, text="Starting download...")
    for i, item in enumerate(files, start=1):
        folder, name, file_url = item
        progress.progress(i / len(files), text=f"Downloading {name}")
        try:
            resp = client.fetch(file_url)
        except HttpError as exc:
            results.append((False, f"{folder}/{name}" if folder else name, str(exc)))
            continue
        if resp["status"] >= 400 or not resp["body"]:
            results.append((False, f"{folder}/{name}" if folder else name, f"HTTP {resp['status']}"))
            continue
        final = filename_from_content_disposition(resp["content_disposition"]) or name
        entries.append((folder, safe_filename(final, f"attachment_{i}"), resp["body"]))
        results.append((True, f"{folder}/{name}" if folder else name, str(len(resp["body"]))))
    progress.empty()
    return entries, results


def _show_results(results):
    for ok, label, info in results:
        if ok:
            st.markdown(
                f'<div class="edex-result edex-result--ok">✓ {label}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="edex-result edex-result--fail">✕ {label} — {info}</div>',
                unsafe_allow_html=True,
            )


if state and state["mode"] == "categorised":
    files = state["files"]
    epar_id = state.get("epar_id") or "EDEX"
    if not files:
        st.info("No uploaded files found on the Application page.", icon=":material/info:")
    else:
        damage_groups = {f.group for f in files if f.group != APPLICATION_GROUP}
        st.success(
            f"Found {len(files)} file(s) across {len(damage_groups)} damage item(s)"
            + (" plus application-level documents." if any(
                f.group == APPLICATION_GROUP for f in files) else "."),
            icon=":material/check_circle:",
        )
        ordered = sorted(files, key=lambda f: (f.order, f.group, f.category, f.filename.lower()))
        for f in ordered:
            st.markdown(f"`{f.group}/{f.category}/` **{f.filename}**")

        if st.button(f"Download all {len(files)} as a folder zip", type="primary"):
            todo = [(f"{f.group}/{f.category}", f.filename, f.url) for f in ordered]
            entries, results = _download_all(todo)
            st.session_state["cloud_zip"] = {
                "zip": build_tree_zip(entries) if entries else b"",
                "name": f"{safe_filename(epar_id, 'EDEX')}-attachments.zip",
                "results": results,
            }

elif state and state["mode"] == "flat":
    files = only_files(state["attachments"])
    if not files:
        st.info("No attachments detected on that page.", icon=":material/info:")
    else:
        preselected = {a.url for a in filter_by_extension(files, state["extensions"])}
        rows = [
            {"Download": a.url in preselected, "File": a.filename or a.url,
             "Type": (a.ext.upper() if a.ext else "—"), "Address": a.url}
            for a in files
        ]
        edited = st.data_editor(
            rows, hide_index=True, use_container_width=True,
            disabled=["File", "Type", "Address"],
            column_config={"Download": st.column_config.CheckboxColumn("Get", width="small")},
        )
        selected = [a for a, r in zip(files, edited) if r["Download"]]
        if st.button(f"Download {len(selected)} selected", type="primary", disabled=not selected):
            todo = [("", a.filename or f"attachment_{i}", a.url) for i, a in enumerate(selected, 1)]
            entries, results = _download_all(todo)
            flat = [(name, data) for _folder, name, data in entries]
            names = dedupe_names([n for n, _ in flat])
            flat = [(nn, data) for nn, (_n, data) in zip(names, flat)]
            st.session_state["cloud_zip"] = {
                "zip": build_zip(flat) if flat else b"",
                "name": "edex-attachments.zip",
                "results": results,
            }

prepared = st.session_state.get("cloud_zip")
if prepared:
    render_nosection()
    ok = sum(1 for r in prepared["results"] if r[0])
    st.subheader(f"Downloaded {ok} of {len(prepared['results'])} file(s)", anchor=False)
    if prepared["zip"]:
        st.download_button(
            "Save the zip", data=prepared["zip"], file_name=prepared["name"],
            mime="application/zip", type="primary",
        )
    _show_results(prepared["results"])

render_nosection()
render_footer()
