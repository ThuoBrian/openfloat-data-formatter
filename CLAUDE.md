# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

OpenFloat Data Formatter (ADF) — a Python tool that transforms Process Maker airtime disbursement exports (CSV/Excel) into the OpenFloat SaaS upload template format. The pipeline is: **Process Maker CSV → validate → normalize → map → output OpenFloat-ready .xlsx**.

## Reference Data in `docs/`

| File | Purpose |
|---|---|
| `1_ProcessMaker_Bridges_Combined_Airtime_Report.csv` | Sample Process Maker input (196 rows, 11 columns) |
| `openfloat-transactions-template.xlsx` | Target OpenFloat upload template — `Accounts` sheet (8 cols) + `Allowed Types` sheet (63 types). The `Allowed Types` sheet must be copied verbatim in output |
| `Final_Report_11364-26082507344787.xlsx` | Example of a completed OpenFloat transaction statement (for reference) |

These files are tracked despite `.gitignore` excluding `*.csv`/`*.xlsx` (force-added).

## Key Domain Rules

**Phone normalization**: strip whitespace/special chars, remove `254` or `0` prefix (only if result would be >9 digits after removal) → keep 9 digits → prepend `254` for output. Reject numbers not exactly 9 digits after stripping. Edge case: `254012345678` → strip `254` → `012345678` (already 9 digits, keep leading zero) → `254012345678`.

**Network → Account Type mapping**: `Safaricom` → `Safaricom Prepaid`, `Airtel` → `Airtel Prepaid`, `Airtel Postpaid` → `Airtel Postpaid`, `Telkom` → `Telkom Kenya Prepaid`, `Telkom Postpaid` → `Telkom Kenya Postpaid`. Unmapped networks → hard error. Mapping is case-sensitive.

**Consent filter**: exclude rows where `consent ≠ "Yes"` (case-insensitive). Never silently drop data — always report what was filtered and why.

**Duplicates**: same `airtime_phone` appearing more than once → warning (not auto-deduplicated).

**Amount validation**: coerce to positive number; reject ≤0 or non-numeric; warn above KES 10,000 threshold.

**Remark / case_remark**: the `Remark` output column is built from the input `case_remark` column when present — a manually-typed reference in the fixed format `C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>` (e.g. `C#37166 22505AA RESP AIRTIME-KSH29400 d05`). A well-formed value is reformatted to `Case #<case_number> | <project_code> | RESP | AIRTIME KSH <amount> | <activity_code>`. Priority order: well-formed `case_remark` → raw `case_remark` text verbatim (soft warning, parse failure) → legacy `"{project_name} - {Project_Activity}"` (when `case_remark` is empty/absent). The amount embedded in `case_remark` is cross-checked against the row's real `amount` column and warns (soft) on mismatch, but does not block the row. Any free-text value written to the output (Remark, Account Name) is sanitized against Excel formula injection (a leading `=`, `+`, `-`, or `@` gets a `'` prefix) before being written — see `writer.py::_sanitize_cell_value`.

**Allowed Types**: 63 entries in the template. Note `SPA NAKURU RURAL ` has a trailing space — must be preserved verbatim.

## Architecture

```
src/backend/
  config.py        # Settings (Pydantic BaseSettings, env-overridable)
  models.py        # Pydantic v2 data models (InputRow, OutputRow, ValidationReport, etc.)
  normalizer.py    # Phone number & amount normalization (pure functions)
  mapper.py        # Network → Account Type mapping (5-entry lookup)
  validator.py     # Input validation: consent, phone, network, amount, duplicates
  transformer.py   # Pipeline orchestrator: read → validate → normalize → map → build output
  writer.py        # OpenFloat Excel output (openpyxl, two-sheet)
  main.py          # FastAPI app: POST /transform, /validate, GET /health
src/frontend/
  app.py           # Streamlit UI: upload, preview, validate, download
src/tests/         # pytest suite (68 tests)
```

Tech stack: Python 3.11+, Pandas, OpenPyXL, FastAPI, Pydantic v2, Streamlit.

## Build & Run Commands

```bash
python -m venv venv && source venv/bin/activate   # Create/activate venv
pip install -r requirements.txt                   # Install dependencies
PYTHONPATH=src pytest src/tests/ -v               # Run all tests (68 tests)
PYTHONPATH=src pytest src/tests/test_normalizer.py -v  # Run single test module
PYTHONPATH=src pytest src/tests/ -k "test_phone" -v    # Run tests by name pattern
uvicorn src.backend.main:app --reload             # Run FastAPI server (port 8000)
streamlit run src/frontend/app.py                 # Run Streamlit UI (port 8501)
```

## Error Handling Convention

Hard errors (invalid phone, unmapped network, invalid amount, non-Yes consent) → exclude row from output, report in validation errors. Soft warnings (duplicates, high amounts) → include row, surface in validation warnings. The validator never mutates the DataFrame.