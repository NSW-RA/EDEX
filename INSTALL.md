# Installing EDEX on your PC

EDEX runs on your own computer and signs in with **your** SmartyGrants account.
Follow these steps once. It takes about 10 minutes.

You'll need:
- A Windows PC
- Your normal SmartyGrants / NSW login
- About 10 minutes and ~300 MB of disk space

---

## Step 1 — Install Python (one time)

1. Go to **https://www.python.org/downloads/** and click the big **Download Python** button.
2. Run the downloaded installer.
3. **IMPORTANT:** on the first screen, tick the box **"Add python.exe to PATH"** at the bottom, *then* click **Install Now**.
4. When it finishes, click **Close**.

> If you already have Python, you can skip this step.

---

## Step 2 — Get the EDEX files

**Option A — from GitHub** (if you've been given access to the repository)
1. Open the repo page, click the green **Code** button → **Download ZIP**.
2. Right-click the downloaded ZIP → **Extract All** → choose a location like your Desktop.

**Option B — from a shared copy**
1. Copy the `EDEX` folder your colleague shares to somewhere on your PC (e.g. your Desktop).
2. If it contains a `.venv` folder, delete that one folder (it's specific to their PC; Step 3 rebuilds it).

---

## Step 3 — Set up EDEX (one time)

1. Open the `EDEX` folder.
2. Double-click **`setup_edex.bat`**.
3. A black window opens and installs the packages. Let it finish until it says **"Setup complete."**
4. Press a key to close it.

> If Windows shows a blue "Windows protected your PC" box, click **More info → Run anyway** (this is normal for scripts that aren't signed).

---

## Step 4 — Start EDEX (every time you use it)

1. First, open **SmartyGrants** in your normal browser and make sure you're **logged in**.
2. In the `EDEX` folder, double-click **`run_edex.bat`**. EDEX opens in your web browser; keep the little black window open while you work.
3. To use it: enter a SmartyGrants application number → under **① Your sign-in**, click **"Read my sign-in from my browser"** (or paste it, if asked) → **Fetch attachments** → save the zip.
4. To stop, just close the black window.

---

## If something goes wrong

- **"python is not recognized"** when running setup → Python wasn't added to PATH. Re-run the Python installer (Step 1), choose **Modify**, and make sure **"Add Python to environment variables"** is ticked.
- **"Couldn't read your sign-in automatically"** → your browser blocks it. Make sure you're logged into SmartyGrants, then use **"Paste it manually instead"** and follow the two steps shown.
- **"Not signed in — cookie missing or expired"** → your sign-in has lapsed. Log into SmartyGrants again in your browser, then read/paste it again.
- **Anything else** → send your colleague a photo of the message.
