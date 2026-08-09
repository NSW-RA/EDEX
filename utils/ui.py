"""Streamlit rendering helpers: NSW-branded page chrome and HTML fragments.

Mirrors the EPAR Checker Tool's approach so the two tools share one look: all
HTML lives in static/html templates; all styling lives in static/css and the
locally vendored NSW Design System stylesheet (no CDN dependency, so the
branding still renders inside firewalled government networks).
"""

from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

STATIC_DIR = Path(__file__).parent.parent / "static"


@lru_cache(maxsize=None)
def _load(*relative_path: str) -> str:
    """Read a static template once per process; templates never change at runtime."""
    return (STATIC_DIR / Path(*relative_path)).read_text(encoding="utf-8")


def render_masthead() -> None:
    st.markdown(_load("html", "masthead.html"), unsafe_allow_html=True)


def render_nosection() -> None:
    st.markdown(_load("html", "nosection.html"), unsafe_allow_html=True)


def render_splash() -> None:
    """Branded loading splash, shown once per session on first page load."""
    if st.session_state.get("_splash_shown"):
        return
    st.session_state["_splash_shown"] = True
    st.markdown(_load("html", "splash.html"), unsafe_allow_html=True)


def render_header(title: str) -> None:
    """Inject the stylesheets and render the NSW masthead, header, and title bar."""
    # Inlined rather than served via Streamlit's static file route: on some
    # deployment hosts that route is unreliable, and a missing stylesheet
    # leaves the raw SVG logos and markup unstyled.
    st.markdown(
        f"<style>{_load('vendor', 'nsw-design-system-3.24.10.css')}</style>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<style>{_load('css', 'main.css')}</style>", unsafe_allow_html=True)
    render_masthead()
    st.markdown(_load("html", "header.html"), unsafe_allow_html=True)
    st.markdown(
        f'<div class="header-bar" id="main-content"><h1 class="header-title">{escape(title)}</h1></div>',
        unsafe_allow_html=True,
    )


def render_intro() -> None:
    st.markdown(_load("html", "intro.html"), unsafe_allow_html=True)


def render_footer() -> None:
    st.markdown(_load("html", "footer.html"), unsafe_allow_html=True)


def render_status(browser_live: bool) -> None:
    """A single pill reporting whether the browser session is running."""
    if browser_live:
        cls, text = "edex-status--on", "Browser session live"
    else:
        cls, text = "edex-status--off", "Browser not started"
    st.markdown(
        f'<span class="edex-status {cls}"><span class="edex-status__dot"></span>{escape(text)}</span>',
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, message: str) -> None:
    st.markdown(
        '<div class="nsw-empty-state">'
        f'<p class="nsw-empty-state__title">{escape(title)}</p>'
        f'<p class="nsw-empty-state__message">{escape(message)}</p></div>',
        unsafe_allow_html=True,
    )


def render_summary(count: int, url: str) -> None:
    plural = "attachment" if count == 1 else "attachments"
    st.markdown(
        '<div class="edex-summary">'
        f'<p class="edex-summary__count">{count} {plural} found</p>'
        f'<p class="edex-summary__url">{escape(url)}</p></div>',
        unsafe_allow_html=True,
    )
