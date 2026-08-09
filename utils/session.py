"""Shared access to the one cached browser session.

Kept in its own module so both app.py and the pages can import it without
importing app.py itself (importing app.py would re-run its page chrome).
"""

import streamlit as st

from core.browser import BrowserSession


@st.cache_resource
def get_session() -> BrowserSession:
    """One browser for the whole app process, created lazily (not yet started)."""
    return BrowserSession()
