# OpenFloat Data Formatter — Setup Guide

Turns a Process Maker airtime disbursement export into an OpenFloat-ready
upload file. Everything runs on your own laptop — your data is never sent
anywhere remote.

## Before You Start

- You need an internet connection **the first time you install/run it** (to
  download the app, Python, and the required packages, roughly 150–250 MB).
  After that, it runs fully offline.
- Windows 10 or 11.
- Nothing needs to be pre-installed — no Python, no Git. The installer sets
  everything up.

## Installing (first time only)

1. Open **PowerShell** (search for it in the Start menu).
2. Paste this command and press Enter:

   ```powershell
   irm https://raw.githubusercontent.com/ThuoBrian/openfloat-data-formatter/main/install/install.ps1 | iex
   ```

3. A window will ask where to install the app (Desktop by default) — pick a
   folder or just press OK.
4. It downloads the app and starts setting up automatically — this continues
   in the "Starting the App" steps below.

## Starting the App

1. **First time**: happens automatically at the end of installing (above).
   **Later**: go to the folder you installed into and double-click
   **`run.bat`**.
2. A black command window will pop up — this is normal. **Don't close it**
   while you're using the app; closing it stops the app.
3. **First run only**: setup takes a few minutes (installing Python and
   packages). You'll see progress messages in the black window.
4. Once ready, your browser will open automatically to a page titled
   "OpenFloat Data Formatter". If it doesn't open on its own, go to
   `http://localhost:8501` in your browser.
5. Every run after the first takes just a few seconds.
6. **To stop the app**, close the black command window (closing just the
   browser tab leaves it running in the background).

## Getting Updates

Re-run the same PowerShell command from **Installing** above. It re-downloads
the latest version into the same folder and starts it — no need to remove
anything first.

## Using the App

1. Upload your Process Maker CSV or Excel export.
2. Check the **Data Preview** and **Validation Report** — this tells you how
   many rows are valid and flags anything wrong (missing consent, bad phone
   numbers, unrecognized networks, duplicate numbers, etc.).
3. Click **Download OpenFloat Excel** to get the file ready for upload to
   OpenFloat.

## FAQ

**Does my data leave my laptop?**
No. The app processes your file locally; nothing is uploaded to the internet
(only the one-time setup step downloads Python packages, not your data).

**Where does the downloaded file go?**
Wherever your browser normally saves downloads (usually your Downloads
folder).

**The black window shows an error and closed.**
Try double-clicking `run.bat` again. If it still fails, take a screenshot of
the error and send it to whoever gave you this tool.
