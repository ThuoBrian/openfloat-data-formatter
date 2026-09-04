# OpenFloat Data Formatter

Transforms Process Maker airtime disbursement exports (CSV/Excel) into the
OpenFloat SaaS upload template format.

```
Process Maker CSV → validate → normalize → map → OpenFloat-ready .xlsx
```

## For end users

Not a developer? See **[GUIDE.md](GUIDE.md)** — one PowerShell command
installs and runs the app, no Python or Git required.

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

## What it does

- **Validates** input rows: consent, phone format, network, amount, duplicates
  — reports every issue, never silently drops data.
- **Normalizes** phone numbers to `254XXXXXXXXX` and coerces amounts to
  positive floats.
- **Maps** network names to OpenFloat account types (Safaricom, Airtel,
  Telkom, ...).
- **Builds** the Remark column from a manually-typed `case_remark` reference
  when present, falling back to `project_name - Project_Activity`.
- **Writes** a two-sheet `.xlsx` (Accounts + Allowed Types) matching the
  OpenFloat upload template exactly.

See [CLAUDE.md](CLAUDE.md) for the full domain rules and architecture.

## Project structure

```
src/openfloat_formatter/   the Python package: validation, normalization,
                           mapping, Excel output, statement reporting,
                           FastAPI app, and the Streamlit UI (ui/app.py)
tests/                      pytest suite
docs/                       reference data (OpenFloat template, notes)
scripts/                    maintenance scripts (e.g. template generator)
install/                    one-liner installer for non-technical users
```

## Stack

Python 3.11+ · Pandas · OpenPyXL · FastAPI · Pydantic v2 · Streamlit
