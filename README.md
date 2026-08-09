# EDEX — Attachment Downloader

A local Streamlit tool for the NSW Reconstruction Authority. Sign in once to a
portal (Microsoft SSO / MFA), paste the address of a page, and EDEX collects
every attachment link so you can download them all in one zip.

Sibling to the EPAR Checker Tool — same NSW branding and layout.

## How it works

EDEX drives a real, headed browser via **Playwright**, using a persistent
profile so your sign-in survives across the app's reruns. Attachments are
fetched through that signed-in session, so files behind the login come through
with the right cookies.

```
app.py               Main page: sign in, paste a URL, fetch attachments
pages/1_Results.py   Review found attachments, pick some, download as a zip
pages/2_Guide.py     User guide
core/browser.py      Playwright persistent session on a worker thread
core/scraper.py      Resolve/de-duplicate/filter links (pure, tested)
core/downloader.py   Filenames + zip bundling (pure, tested)
core/models.py       Attachment / DownloadResult dataclasses
utils/ui.py          NSW-branded page chrome
utils/session.py     The one cached browser session
static/              NSW Design System CSS, HTML chrome, logos
tests/               Unit tests for the pure logic
```

## Setup (first time)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```bash
streamlit run app.py
```

Then in the app:

1. **Open browser & sign in** — a browser window opens; complete your normal
   portal sign-in there (once per session).
2. **Fetch attachments** — EDEX reads the page and lists every link.
3. **Download** — tick the files you want and save them as a single zip.

## Tests

```bash
pytest
```

The tests cover the pure logic (link resolution/filtering, filename handling,
zip bundling). The browser layer is exercised manually against the real portal.

## Notes

- **Local only.** EDEX runs on your machine; nothing is uploaded. Your sign-in
  lives in `.edex_profile/` (git-ignored).
- **JavaScript-heavy pages / files behind buttons.** v1 collects `<a href>`
  links. If a page builds itself after load, let it finish loading in the browser
  window before fetching. Files served from an address without a file extension
  (e.g. `/download?id=123`) are included when you clear the *File types* filter.
