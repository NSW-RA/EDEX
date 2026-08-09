"""User Guide page: how to sign in and download attachments."""

import streamlit as st

st.set_page_config(page_title="EDEX — Guide", layout="wide")

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

from utils.ui import render_footer, render_header, render_nosection

render_header("EDEX — User Guide")
render_nosection()

st.markdown(
    """
### What EDEX does
EDEX opens a normal browser window, lets you sign in to the portal the usual way
(including Microsoft single sign-on and MFA), then reads a page you point it at
and collects every attachment link so you can download them all at once.

### Before your first use
The browser engine needs to be installed once. Open a terminal in the EDEX
folder and run:

```
python -m playwright install chromium
```

### Step by step
1. **Enter the application.** For a SmartyGrants application you can paste just
   its number (e.g. `4606199`) or any of its page addresses — EDEX automatically
   goes to the application's **Files** tab, which lists every attachment. For any
   other portal, paste the full address of the page that shows the files.
2. **Open browser & sign in.** Press **1 · Open browser & sign in**. A browser
   window opens — complete your normal sign-in there. You only need to do this
   once per session; EDEX remembers it.
3. **Fetch attachments.** Back in EDEX, press **2 · Fetch attachments**. EDEX
   reads the Files tab and lists every attachment it found.
4. **Pick and download.** On the Results page, tick the files you want (the file
   types you chose are ticked for you), then press **Download** and save them as
   a single zip.

### Sorting into folders (SmartyGrants EPAR)
Leave **"Sort into folders by damage item & evidence type"** on (the default) and
EDEX reads the application's Damage Information grid and organises the download
into folders — one per damage item, split by evidence type:

```
<EPAR ID>-attachments.zip
├── Damage 01 — CBRS1 (Carrowbrook Road)/
│   ├── Pre-Disaster Evidence/
│   ├── Damage Evidence/
│   └── Cost Estimate Evidence/
├── Damage 02 — .../
└── Application-level/
    ├── Public Liability Insurance/
    └── Other Supporting Documents/
```

Each file is placed by **where it sits in the grid** — its row is the damage
item, its column is the evidence type — so two files with the same name under
different damage items never clash. Turn the toggle off for a single flat list
(this also works for non-SmartyGrants pages).

### Finding the application number
It's the number in the SmartyGrants address bar —
`manage.smartygrants.com.au/application/`**`4606199`**`/…` — not the EPAR ID
(like `EP11700000005`).

### Tips
- **Nothing found?** Some portals build the page after it loads or hide files
  behind buttons rather than plain links. Make sure the page has fully loaded in
  the browser window before you fetch.
- **Files without a file extension.** Some portals serve downloads from an
  address like `/download?id=123`. Clear the *File types* box on the main page to
  include those, then rely on the ticks to choose what you want.
- **Session expired.** If downloads start failing, your sign-in may have timed
  out. Go back, press **Open browser & sign in** again, and re-fetch.

### Privacy
EDEX runs entirely on your computer. Your sign-in stays in a local browser
profile in the EDEX folder; nothing is sent anywhere except the portal you are
already signed in to.
"""
)

if st.button("← Back to start", type="secondary"):
    st.switch_page("app.py")

render_nosection()
render_footer()
