"""EDEX — Attachment Downloader (main page).

Sign in once in a real browser window (Microsoft / SSO / MFA), paste the address
of the page that holds the files, and EDEX collects every attachment link. The
results, review, and download happen on the Results page.
"""

import logging

import streamlit as st

st.set_page_config(page_title="EDEX — Attachment Downloader", layout="wide")

# Widen the main content container (matches the EPAR Checker Tool).
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

from core.browser import BrowserError, BrowserSession
from core.scraper import DEFAULT_EXTENSIONS, build_attachments, normalize_target_url
from core.smartygrants import parse_application
from utils.session import get_session
from utils.ui import (
    render_footer,
    render_header,
    render_intro,
    render_nosection,
    render_splash,
    render_status,
)

logger = logging.getLogger(__name__)


def _ensure_started(session: BrowserSession) -> None:
    if not session.alive:
        session.start()


def _report_browser_error(exc: BrowserError) -> None:
    import sys

    message = str(exc)
    low = message.lower()
    if "executable doesn't exist" in low or "playwright install" in low:
        st.error(
            "Chromium isn't installed for the Python that's running EDEX.\n\n"
            "The fix: **close this and start EDEX by double-clicking "
            "`run_edex.bat`** — it uses the set-up environment that already has "
            "the browser. (If you launched from PyCharm's Run button instead, "
            "that's the cause — it uses a different Python.)\n\n"
            f"Running under: `{sys.executable}`\n\nDetails: {message[:300]}",
            icon=":material/error:",
        )
    else:
        st.error(f"Browser problem: {message[:600]}", icon=":material/error:")


render_splash()
render_header("EDEX — Attachment Downloader")
render_intro()
render_nosection()

session = get_session()

# ---- Sign-in status ------------------------------------------------------
render_status(session.alive)
render_nosection()

st.header("Find attachments on a page", anchor=False)

url = st.text_input(
    "SmartyGrants application number or page address",
    key="page_url",
    placeholder="4606199   or   https://manage.smartygrants.com.au/application/4606199/files",
    help="For a SmartyGrants application, paste its number or any of its page "
    "addresses — EDEX goes straight to the Files tab. For any other portal, paste "
    "the full address of the page that shows the files.",
)

_, _is_sg = normalize_target_url(url)

categorise = st.toggle(
    "Sort into folders by damage item & evidence type (SmartyGrants EPAR)",
    value=True,
    disabled=not _is_sg,
    help="Reads the application's damage grid and organises the download into "
    "folders: Damage 01 / Pre-Disaster Evidence, Damage Evidence, Cost Estimate "
    "Evidence, plus an Application-level folder for insurance and supporting docs. "
    "Turn off for a single flat list.",
)

# The two modes read different pages: the Application page has the damage grid
# (needed for foldering); the Files tab is the flat all-attachments list.
_tab = "application" if (categorise and _is_sg) else "files"
_target, _routed = normalize_target_url(url, tab=_tab)
if _routed:
    _where = "Application page (with the damage grid)" if _tab == "application" else "Files tab"
    st.caption(f"Will read the SmartyGrants **{_where}**: {_target}")

extensions = st.multiselect(
    "File types to look for",
    options=list(DEFAULT_EXTENSIONS),
    default=["pdf", "docx", "xlsx", "xls", "csv", "zip", "jpg", "jpeg", "png"],
    help="Only these file types are pre-ticked on the next screen. Leave empty to "
    "pre-tick everything. (Ignored in folder-sorting mode, which keeps every file.)",
)

col_signin, col_fetch = st.columns(2)

with col_signin:
    if st.button("1 · Open browser & sign in", type="secondary", use_container_width=True):
        try:
            with st.spinner("Opening a browser window..."):
                _ensure_started(session)
                # Navigating to the target page triggers the SSO redirect so the
                # sign-in lands you where you need to be. Blank if no URL yet.
                session.goto(_target or "about:blank")
            st.success(
                "Browser window opened. Complete your sign-in there, then come "
                "back and press **Fetch attachments**.",
                icon=":material/check_circle:",
            )
        except BrowserError as exc:
            _report_browser_error(exc)

with col_fetch:
    if st.button("2 · Fetch attachments", type="primary", use_container_width=True):
        want_categorised = categorise and _is_sg
        target, _ = normalize_target_url(url, tab="application" if want_categorised else "files")
        if not target:
            st.error("Enter an application number or page address first.", icon=":material/error:")
        elif not session.alive:
            st.error(
                "Open the browser and sign in first (button on the left).",
                icon=":material/error:",
            )
        else:
            try:
                if want_categorised:
                    with st.spinner("Reading the damage grid and sorting files..."):
                        result = session.scrape(target, want_html=True)
                        parsed = parse_application(result.get("html", ""), result["page_url"])
                    st.session_state["scrape"] = {
                        "mode": "categorised",
                        "files": parsed.files,
                        "epar_id": parsed.epar_id,
                        "page_url": result["page_url"],
                    }
                    logger.info(
                        "Categorised %d file(s) for %s", len(parsed.files), parsed.epar_id
                    )
                else:
                    with st.spinner("Reading the page for attachments..."):
                        result = session.scrape(target)
                    attachments = build_attachments(result["links"], result["page_url"])
                    st.session_state["scrape"] = {
                        "mode": "flat",
                        "attachments": attachments,
                        "page_url": result["page_url"],
                        "title": result.get("title", ""),
                        "extensions": extensions,
                    }
                    logger.info("Found %d link(s) on %s", len(attachments), result["page_url"])
                st.switch_page("pages/1_Results.py")
            except BrowserError as exc:
                _report_browser_error(exc)


render_nosection()
render_footer()
