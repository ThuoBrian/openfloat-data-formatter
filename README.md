# OpenFloat Data Formatter

[![Tests](https://github.com/ThuoBrian/openfloat-data-formatter/actions/workflows/tests.yml/badge.svg)](https://github.com/ThuoBrian/openfloat-data-formatter/actions/workflows/tests.yml)

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

On a Mac? The one-click installer is Windows-only — ask whoever gave you
this tool to set it up, or use the [developer setup](#for-developers) below.

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

Filling in data by hand? Use **`docs/processmaker-input-template.xlsx`** (in
your install folder) — it has the correct headers, valid example rows,
dropdowns for consent and network, and an Instructions sheet explaining the
format rules.

### Limitations

- Expects Process Maker's specific column layout (see
  `processmaker-input-template.xlsx`) — a differently-shaped export will fail
  validation, not get silently reinterpreted.
- Phone normalization assumes Kenyan numbers (9 local digits, `254` country
  code); other country formats are rejected as invalid.
- Network → Account Type mapping is a fixed, case-sensitive lookup (see
  [CLAUDE.md](CLAUDE.md#key-domain-rules)); an unrecognized or
  differently-cased network name is a hard error, not a best-effort guess.
- Duplicate phone numbers are flagged, not auto-deduplicated — you decide
  which row is correct.
- It prepares the upload file and reads statements back; it does not talk to
  the OpenFloat API or submit anything on your behalf.
- The one-click installer is Windows-only (see [GUIDE.md](GUIDE.md)).

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
uv run ruff check . && uv run mypy   # lint + type-check (CI enforces these too)
```

Pipeline: `Process Maker CSV → validate → normalize → map → OpenFloat-ready .xlsx`.
Full domain rules and architecture: [CLAUDE.md](CLAUDE.md).
Development pitfalls and non-obvious behaviors: [docs/GOTCHA.md](docs/GOTCHA.md).

### HTTP API

The same functionality is exposed by a FastAPI server (`./start.sh api`),
with interactive docs at `http://localhost:8000/docs`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/transform` | POST | Upload a Process Maker export, get the OpenFloat-ready file + validation report |
| `/validate` | POST | Validation report only — no output file |
| `/statement-report` | POST | Analyze OpenFloat Transaction Statement file(s), optionally reconciled against the original input |
| `/health` | GET | Liveness check |

### Configuration

All settings have defaults and are optional to override. Copy `.env.example`
to `.env` and edit, or set the environment variable directly:

| Variable | Default | Description |
|---|---|---|
| `MAX_AMOUNT_THRESHOLD` | `10000` | Airtime amount (KES) above which a row gets a soft warning |
| `DEFAULT_COUNTRY_PREFIX` | `254` | Country code prepended to normalized phone numbers |
| `REQUIRED_CONSENT_VALUE` | `Yes` | Value required in the `consent` column to include a row (case-insensitive) |
| `OPENFLOAT_TEMPLATE_PATH` | `docs/openfloat-transactions-template.xlsx` | Path to the OpenFloat template (relative to project root) |

See `src/openfloat_formatter/config.py` for the full `Settings` model.

### Project structure

```
src/openfloat_formatter/   the Python package: validation, normalization,
                           mapping, Excel output, statement reporting,
                           FastAPI app, and the Streamlit UI (ui/app.py)
tests/                      pytest suite
docs/                       reference data (OpenFloat template, fillable input
                           template, GOTCHA.md dev notes)
scripts/                    maintenance scripts (e.g. template generator)
install/                    one-liner installer for non-technical users
```

### Stack

Python 3.11+ · Pandas · OpenPyXL · FastAPI · Pydantic v2 · Streamlit

## Contributing

Bug reports and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
for setup, testing, and the PR process.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).