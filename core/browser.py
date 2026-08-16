"""A long-lived, signed-in browser the Streamlit UI can drive across reruns.

Why a worker thread:
  Streamlit reruns the script top-to-bottom on every interaction and runs it
  inside an asyncio event loop. Playwright's *sync* API refuses to run inside a
  running event loop. So we hand all Playwright work to a single dedicated
  thread that owns the browser for the life of the process; the UI thread talks
  to it over a command queue and blocks for the reply. One browser, one profile,
  reused across every rerun — which is exactly what an interactive SSO/MFA login
  needs (you sign in once and the session persists).

The browser runs *headed* on purpose: the whole point is that you complete the
Microsoft / MFA sign-in yourself in a real window, once.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, Callable

# Where the persistent Chromium profile lives (cookies, SSO session). Kept
# beside the app so it survives restarts; add it to .gitignore.
PROFILE_DIR = Path(__file__).parent.parent / ".edex_profile"

# A command is a callable run on the worker thread with (context, page).
_Command = Callable[[Any, Any], Any]


class BrowserError(RuntimeError):
    """Raised in the UI thread when a worker command fails."""


class BrowserSession:
    """Owns one Playwright persistent context on a dedicated thread."""

    def __init__(self, profile_dir: Path = PROFILE_DIR, headless: bool = False):
        self._profile_dir = Path(profile_dir)
        self._headless = headless
        self._commands: "queue.Queue[tuple[_Command, queue.Queue] | None]" = queue.Queue()
        self._ready = threading.Event()
        self._start_error: Exception | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Launch the browser and block until it is ready (or raise).

        Idempotent and restartable: a ``threading.Thread`` can only be started
        once, so each attempt builds a *fresh* worker thread. If a previous
        attempt failed (e.g. the browser wasn't installed) the worker exits and
        this can be called again to retry — instead of crashing with
        "threads can only be started once".
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self._commands = queue.Queue()
        self._ready = threading.Event()
        self._start_error = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="edex-browser", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._start_error is not None:
            raise BrowserError(str(self._start_error)) from self._start_error

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._closed

    def close(self) -> None:
        if self._closed or self._thread is None:
            return
        self._closed = True
        self._commands.put(None)

    def _run(self) -> None:
        """Worker-thread entry point: own the browser, service commands."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - import guard
            self._start_error = exc
            self._ready.set()
            return

        try:
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    str(self._profile_dir),
                    headless=self._headless,
                    accept_downloads=True,
                    args=["--start-maximized"],
                    no_viewport=True,
                )
                page = context.pages[0] if context.pages else context.new_page()
                self._ready.set()

                while True:
                    item = self._commands.get()
                    if item is None:
                        break
                    command, reply = item
                    try:
                        reply.put(("ok", command(context, page)))
                    except Exception as exc:  # deliver failure to the UI thread
                        reply.put(("err", exc))

                try:
                    context.close()
                except Exception:
                    pass
        except Exception as exc:
            # Launch failed (commonly: Chromium not installed). Report it to
            # whoever is waiting on start(), and to any pending commands.
            self._start_error = exc
            self._ready.set()

    # ---- command plumbing ------------------------------------------------

    def _submit(self, command: _Command, timeout: float = 300.0) -> Any:
        if not self.alive:
            raise BrowserError("The browser session is not running. Start it again.")
        reply: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self._commands.put((command, reply))
        try:
            status, value = reply.get(timeout=timeout)
        except queue.Empty as exc:
            raise BrowserError("The browser did not respond in time.") from exc
        if status == "err":
            raise BrowserError(str(value)) from value
        return value

    # ---- operations the UI calls ----------------------------------------

    def goto(self, url: str, timeout: float = 120.0) -> str:
        """Navigate the visible page and return the URL it settled on."""

        def _cmd(context, page):
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            return page.url

        return self._submit(_cmd, timeout=timeout + 30)

    def current_url(self) -> str:
        return self._submit(lambda context, page: page.url, timeout=30)

    def scrape(
        self, url: str, settle_ms: int = 1200, timeout: float = 120.0, want_html: bool = False
    ) -> dict:
        """Navigate to `url`, let scripts settle, and read every <a href>.

        Returns {"page_url", "title", "links"} where links is a list of
        (absolute_href, visible_text). The DOM resolves hrefs to absolute for us
        (honouring any <base> tag), so callers get absolute URLs. When
        `want_html` is set, the rendered page HTML is included as "html" (needed
        for the SmartyGrants damage-grid parser).
        """

        def _cmd(context, page):
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            # Best-effort wait for late content; don't fail the scrape if the
            # network never fully idles (long-polling dashboards never do).
            try:
                page.wait_for_load_state("networkidle", timeout=settle_ms + 3000)
            except Exception:
                page.wait_for_timeout(settle_ms)
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => [e.href, (e.textContent || '').trim()])",
            )
            result = {"page_url": page.url, "title": page.title(), "links": links}
            if want_html:
                result["html"] = page.content()
            return result

        return self._submit(_cmd, timeout=timeout + 30)

    def fetch(self, url: str, timeout: float = 180.0) -> dict:
        """Authenticated GET that reuses the signed-in session's cookies.

        Returns {"status", "body", "content_disposition", "content_type"}.
        """

        def _cmd(context, page):
            resp = context.request.get(url, timeout=timeout * 1000)
            headers = resp.headers  # keys are lower-cased by Playwright
            return {
                "status": resp.status,
                "body": resp.body() if resp.ok else b"",
                "content_disposition": headers.get("content-disposition"),
                "content_type": headers.get("content-type"),
            }

        return self._submit(_cmd, timeout=timeout + 30)
