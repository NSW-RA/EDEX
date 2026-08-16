# EDEX — Attachment Downloader

A Streamlit tool for the NSW Reconstruction Authority. Enter a SmartyGrants
application, let EDEX use your SmartyGrants sign-in, and it downloads every
attachment — sorted into folders by damage item and evidence type — as a single
zip.

Sibling to the EPAR Checker Tool — same NSW branding and layout.

## How it works

EDEX authenticates with your SmartyGrants sign-in and fetches the pages and
files over plain HTTP requests — **no browser automation**. That's deliberate:
browser automation is blocked on locked-down government machines, and it can't
run on a shared server. Fetching over HTTP works in both places, so the same
app runs locally *and* deploys to Streamlit Community Cloud.

Your sign-in comes from either:
- **Automatically** reading it from your browser (works when you run EDEX on your
  own machine), or
- **Pasting** it (the fallback, and the only option on the cloud version).

```
app.py                Single-page app: sign-in, fetch, sorted download
core/http_client.py   Cookie-authenticated HTTP client (scrape + fetch)
core/smartygrants.py  Parse the Application damage grid -> categorised files
core/scraper.py       Resolve / de-duplicate / filter links (pure, tested)
core/downloader.py    Filenames, zip building, folder-tree zip (pure, tested)
core/models.py        Attachment / CategorisedFile dataclasses
utils/ui.py           NSW-branded page chrome
static/               NSW Design System CSS, HTML chrome, logos
tests/                Unit tests for the pure logic (35 tests)
```

## For colleagues

Each person runs their own copy and uses their own sign-in. Non-technical
step-by-step instructions are in **[INSTALL.md](INSTALL.md)**.

## Run locally

**Easiest (Windows):** double-click **`setup_edex.bat`** once, then
**`run_edex.bat`** whenever you want EDEX. It opens in your web browser; keep the
little black window open while you work, close it to stop.

**From a terminal:**

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-local.txt
.venv\Scripts\streamlit run app.py
```

Then: enter an application number (e.g. `4606199`) → get your sign-in (auto-read
or paste) → **Fetch attachments** → save the zip.

## Deploy to Streamlit Community Cloud

`requirements.txt` is cloud-safe (no Playwright), so deploying just works. Point
the app's **Main file path** at `app.py`. On the cloud version, the auto-read
button can't see the user's browser, so users paste their sign-in manually.

## Tests

```bash
.venv\Scripts\python -m pytest
```

Cover the pure logic: link resolution/filtering, the SmartyGrants grid parser,
filename handling, and zip/folder-tree building.

## Notes

- **Your sign-in is a live credential.** Locally it stays on your machine. On the
  cloud version it passes through Streamlit's servers — confirm that's acceptable
  for your organisation before sharing it widely.
- **Categorised mode** reads the Application page's damage grid: each file's
  folder is its row (damage item) and its column (evidence type), so files are
  placed correctly even when two share a name. Turn it off for a flat list.
