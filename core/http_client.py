"""Cookie-authenticated HTTP client — the cloud alternative to the browser.

The local app drives a real browser (core.browser) so you can sign in to SSO/MFA
interactively. That can't work on a shared server, where there's no screen to log
into. Instead, the cloud app asks each user to paste their SmartyGrants session
cookie (copied from a tab they're already logged into), and this client replays
that cookie on plain HTTP requests to fetch the Application page and download the
files server-side.

It exposes the same ``scrape`` / ``fetch`` shape as core.browser.BrowserSession,
so the parsing (core.smartygrants) and zipping (core.downloader) code is reused
unchanged.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

# A desktop UA so the portal serves the normal (server-rendered) page.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

# Hosts/paths that mean "you're being asked to log in", i.e. the cookie failed.
_LOGIN_HOST_HINTS = ("login.microsoftonline.com", "login.live.com", "sts.")
_LOGIN_PATH_HINTS = ("/login", "/signin", "/sign-in", "/auth")


class HttpError(RuntimeError):
    """Raised for network failures or an unusable/expired session cookie."""


def cookies_from_local_browser(domain: str = "smartygrants.com.au") -> str:
    """Best-effort read of the domain's cookies from the user's local browser.

    Returns a ``name=value; …`` Cookie header string (including HttpOnly session
    cookies, which a page's document.cookie can't see), or "" if nothing could
    be read. Only meaningful when EDEX runs on the same machine as the browser —
    on a shared server there's no user browser to read.

    Tries Chrome, then Edge, then Firefox. Any failure (e.g. Chrome's newer
    app-bound cookie encryption) is swallowed so the UI can fall back to a
    manual paste.
    """
    try:
        import browser_cookie3
    except Exception:
        return ""
    for loader_name in ("chrome", "edge", "firefox"):
        loader = getattr(browser_cookie3, loader_name, None)
        if loader is None:
            continue
        try:
            jar = loader(domain_name=domain)
            parts = [f"{c.name}={c.value}" for c in jar if c.value]
            if parts:
                return "; ".join(parts)
        except Exception:
            continue
    return ""


def _looks_like_login(final_url: str, html: str) -> bool:
    host = urlsplit(final_url).netloc.lower()
    path = urlsplit(final_url).path.lower()
    if any(h in host for h in _LOGIN_HOST_HINTS):
        return True
    if any(p in path for p in _LOGIN_PATH_HINTS):
        return True
    # SmartyGrants' own login page carries a password field / SSO prompt.
    head = (html or "")[:4000].lower()
    return 'type="password"' in head or "sign in to continue" in head


class HttpClient:
    """A requests.Session pre-loaded with the user's pasted cookie header."""

    def __init__(self, cookie: str, user_agent: str = _USER_AGENT):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        cookie = (cookie or "").strip()
        # Accept a pasted "Cookie:" header (with or without the label) or a bare
        # "name=value; name2=value2" string; send it verbatim so HttpOnly session
        # cookies (which document.cookie can't see) are included.
        if cookie.lower().startswith("cookie:"):
            cookie = cookie.split(":", 1)[1].strip()
        self._cookie = cookie
        if cookie:
            self._session.headers["Cookie"] = cookie

    def _get(self, url: str, timeout: float):
        try:
            return self._session.get(url, allow_redirects=True, timeout=timeout)
        except requests.RequestException as exc:
            raise HttpError(str(exc)) from exc

    def scrape(self, url: str, want_html: bool = False, timeout: float = 60.0) -> dict:
        resp = self._get(url, timeout)
        html = resp.text
        if _looks_like_login(resp.url, html):
            raise HttpError(
                "Not signed in — your cookie is missing or has expired. Copy a fresh "
                "cookie from a SmartyGrants tab you're logged into, then try again."
            )
        soup = BeautifulSoup(html, "html.parser")
        links = [
            (urljoin(resp.url, a.get("href", "")), a.get_text(" ", strip=True))
            for a in soup.select("a[href]")
        ]
        out = {
            "page_url": resp.url,
            "title": soup.title.get_text(strip=True) if soup.title else "",
            "links": links,
        }
        if want_html:
            out["html"] = html
        return out

    def fetch(self, url: str, timeout: float = 180.0) -> dict:
        resp = self._get(url, timeout)
        content_type = resp.headers.get("content-type", "")
        # If the portal handed back its HTML login page instead of the file, the
        # session has lapsed — report it as an auth failure, not a "file".
        if "text/html" in content_type and _looks_like_login(resp.url, resp.text):
            return {"status": 401, "body": b"", "content_disposition": None, "content_type": content_type}
        return {
            "status": resp.status_code,
            "body": resp.content if resp.ok else b"",
            "content_disposition": resp.headers.get("content-disposition"),
            "content_type": content_type,
        }
