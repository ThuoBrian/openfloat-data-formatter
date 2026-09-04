# OpenFloat Data Formatter

Turns Process Maker airtime exports into OpenFloat-ready upload files —
and reports which disbursements actually succeeded. Runs entirely on your
own laptop; your data is never sent anywhere remote.

## Install (no technical skills needed)

1. Open **PowerShell** on Windows 10/11 (search for it in the Start menu).
2. Paste this command and press Enter:

   ```powershell
   irm https://raw.githubusercontent.com/ThuoBrian/openfloat-data-formatter/main/install/install.ps1 | iex
   ```

3. A window asks where to install (Desktop by default) — pick a folder or
   just press OK. The app then sets itself up and opens in your browser.

The first run needs an internet connection (~150–250 MB); after that it
works fully offline.

Full walkthrough — starting the app later, updates, using both modes, FAQ:
**[GUIDE.md](GUIDE.md)**

## What it does

The app has two modes, picked in the sidebar:

- **Transform** — upload a Process Maker export; the app checks every row
  (consent, phone numbers, network, amounts, duplicates), tells you exactly
  what's wrong, and builds the OpenFloat-ready Excel file to upload.
- **Statement Report** — upload the Transaction Statement file(s) OpenFloat
  gives you after disbursement; the app reports successful vs unsuccessful
  transactions and totals per case — and, if you also add your original
  Process Maker file, who was paid, who wasn't, and who never appeared on
  the statement.

Nothing is ever silently dropped or hidden: every filtered row and flagged
discrepancy is reported.

---

## For developers

Requires [uv](https://docs.astral.sh/uv/) (one-liner: `curl -LsSf https://astral.sh/uv/install.sh | sh`).
`uv sync` creates `.venv` and installs the project (editable) with all
dependencies plus the dev tools — no venv activation or PYTHONPATH needed.

```bash
uv sync --python 3.12    # one-time setup (re-run after dependency changes)

./start.sh ui      # Streamlit UI  → http://localhost:8501
./start.sh api     # FastAPI server → http://localhost:8000/docs
./start.sh both    # both at once (start.bat on Windows)

uv run pytest -v   # run the test suite
```

Pipeline: `Process Maker CSV → validate → normalize → map → OpenFloat-ready .xlsx`.
Full domain rules and architecture: [CLAUDE.md](CLAUDE.md).

### Project structure

```
src/openfloat_formatter/   the Python package: validation, normalization,
                           mapping, Excel output, statement reporting,
                           FastAPI app, and the Streamlit UI (ui/app.py)
tests/                      pytest suite
docs/                       reference data (OpenFloat template, notes)
scripts/                    maintenance scripts (e.g. template generator)
install/                    one-liner installer for non-technical users
```

### Stack

Python 3.11+ · Pandas · OpenPyXL · FastAPI · Pydantic v2 · Streamlit