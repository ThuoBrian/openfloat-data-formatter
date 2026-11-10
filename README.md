# OpenFloat Data Formatter

Turns Process Maker airtime exports into files you can upload to OpenFloat, then
tells you which payments actually went through. It runs on your own laptop, and
your data never leaves it.

[![Tests](https://github.com/ThuoBrian/openfloat-data-formatter/actions/workflows/tests.yml/badge.svg)](https://github.com/ThuoBrian/openfloat-data-formatter/actions/workflows/tests.yml)

## Install (no technical skills needed)

1. Open **PowerShell** on Windows 10 or 11 (search for it in the Start menu).
2. Paste this command and press Enter:

   ```powershell
   irm https://raw.githubusercontent.com/ThuoBrian/openfloat-data-formatter/main/install/install.ps1 | iex
   ```

3. A window asks where to install it. The Desktop is the default, so you can
   just press OK. The app sets itself up and opens in your browser.

From then on, start it from the **OpenFloat Data Formatter** shortcut the
installer puts on your Desktop and in the Start menu. To stop it, click
**Close the app** in the sidebar.

The first run downloads about 150–250 MB, so it needs an internet connection.
After that it works offline.

The one-click installer only works on Windows. On a Mac, ask whoever gave you
this tool to set it up, or follow the [developer setup](#for-developers) below.

[GUIDE.md](GUIDE.md) covers the rest: starting the app later, getting updates,
using both modes, and common questions.

## What it does

Pick one of two modes at the top of the page.

**Prepare an OpenFloat upload.** Upload a Process Maker export. The app checks every row (IDs,
phone numbers, network, amounts, duplicates), tells you exactly what's wrong
with each one, and builds the Excel file you upload to OpenFloat. Rows it can't
use are listed with the reason, and you can download them as a sheet to send
back to whoever compiled the export.

**Check payment results.** Upload the Transaction Statement files OpenFloat gives you
after a disbursement. You get successful and unsuccessful transactions, with
totals per case. Add your original Process Maker file as well and it also shows
who was paid, who wasn't, and who never appeared on the statement.

The report downloads as an Excel workbook, with separate sheets for successful
payments, unsuccessful or reversed ones, and the reconciliation lists, each with
a total. A second download is the sheet finance posts from: every statement column plus a **Debit** column
that totals only the payments that went through, with the failed ones shaded
instead of removed.

The app never drops a row quietly. Every row it leaves out and every mismatch
it finds is reported.

Filling in data by hand? Start from **`docs/processmaker-input-template.xlsx`**
in your install folder. It has the right headers, example rows, a dropdown for
the network, and an Instructions sheet with the format rules.

### Limitations

- Every row needs a phone number, a network and an amount. Exports name these
  columns differently, so the app recognises common names (`payphone_number`,
  `service_provider` and so on) and lets you pick the right column in the app
  when it guesses wrong. The ID column is detected the same way (`Staff ID`,
  `Respondent ID`, `respo`, `Beneficiary Ref`).
- Phone numbers are assumed to be Kenyan: 9 local digits plus the `254` country
  code. Numbers in other formats are rejected.
- Networks are matched against a fixed list, and the match is case-sensitive
  (the list is in `src/openfloat_formatter/mapper.py`). A network name the app doesn't
  recognise, or one spelled with different capitals, is rejected rather than
  guessed at.
- Duplicate phone numbers are flagged, not merged. You decide which row is right.
- The app prepares the upload file and reads the statements afterwards. It
  doesn't connect to OpenFloat or submit anything for you.

---

## For developers

You need [uv](https://docs.astral.sh/uv/). It also installs Python for you:
`just sync` uses Python 3.12, and the project supports 3.11 and later.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
```

`uv sync` creates `.venv` and installs the project in editable mode with its
dependencies and dev tools, so there's no virtualenv to activate and no
`PYTHONPATH` to set.

Everyday commands run through [just](https://just.systems/)
(`winget install Casey.Just`, `brew install just`, or `uv tool install rust-just`).
Run `just` on its own to see every recipe.

```bash
just sync     # first-time setup; re-run after dependency changes

just ui       # Streamlit UI at http://localhost:8501
just api      # FastAPI server, docs at http://localhost:8000/docs
just both     # both in one terminal; Ctrl+C stops both

just test     # test suite; extra args pass through (just test -k test_phone)
just check    # lint, type-check and tests, the same checks CI runs

just shortcut # Desktop + Start menu shortcut that launches this checkout
```

If you don't have just, each recipe in the `justfile` is a thin `uv run ...`
wrapper you can run directly.

The pipeline is `Process Maker CSV → validate → normalize → map → OpenFloat-ready .xlsx`.
[docs/GOTCHA.md](docs/GOTCHA.md) lists the things that caught us out during
development.

### HTTP API

`just api` serves the same features over HTTP, with interactive docs at
`http://localhost:8000/docs`:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/transform` | POST | Upload a Process Maker export and get the OpenFloat `.xlsx` back (422 if every row was left out) |
| `/validate` | POST | Validation report only, no output file |
| `/statement-report` | POST | Analyse one or more OpenFloat Transaction Statements, optionally reconciled against the original input |
| `/health` | GET | Confirms the server is running |

`/transform` and `/validate` take two optional form fields.
`account_name_column` names the input column that becomes `Account Name`; leave
it out and the column is detected from the headers. `project_code` completes a
short `C#<case>` reference into the full Remark.

### Configuration

Every setting has a default. To change one, copy `.env.example` to `.env` and
edit it, or set the environment variable directly. The installer keeps your
`.env` when you update.

Both the app and the HTTP API read these. In the app they are starting values:
the controls named below begin with them, and whatever you change there
applies to that upload only.

| Variable | Default | Description |
| --- | --- | --- |
| `MAX_AMOUNT_THRESHOLD` | `10000` | Amount in KES above which a row gets a warning. In the app: **Advanced settings** in the sidebar |
| `DEFAULT_COUNTRY_PREFIX` | `254` | Country code put in front of normalized phone numbers, 1 to 3 digits. In the app: **Advanced settings** |
| `PROJECT_CODE` | *(unset)* | Completes a short `C#<case>` reference into the full Remark. A `project_code` column in the upload takes priority row by row. In the app: the **Project code** box |
| `ACCOUNT_NAME_COLUMN` | *(detected)* | Input column used for the output `Account Name`. If a file doesn't have it, the column is detected from the headers instead. In the app: pre-selected in **Column mapping** |
| `OPENFLOAT_TEMPLATE_PATH` | `docs/openfloat-transactions-template.xlsx` | Path to the OpenFloat template, relative to the project folder |
| `NETWORK_MAP` | the six networks in `config.py` | Network → Account Type lookup. Overriding it takes a full JSON object (`'{"Safaricom":"Safaricom Prepaid"}'`), so it's usually easier to edit `config.py` |

A value the app can't use, such as bad JSON in `NETWORK_MAP` or a `+254`
prefix, stops it with a message naming `.env`; the API refuses to start.

The full `Settings` model is in `src/openfloat_formatter/config.py`.

### Project structure

```text
src/openfloat_formatter/   the Python package: validation, normalization,
                           mapping, Excel output, statement reports, the
                           FastAPI app, and the Streamlit UI (ui/app.py)
tests/                     pytest suite
docs/                      reference data (OpenFloat template, fillable input
                           template) and GOTCHA.md dev notes
scripts/                   maintenance scripts: the input-template and icon
                           generators
install/                   the one-line installer, the shortcut script and
                           the app icon
.streamlit/config.toml     app theme and settings (no usage statistics,
                           20 MB upload limit)
run.bat                    what the shortcut launches: sets up the
                           environment, then starts the app
justfile                   developer commands (run `just` to list them)
```

### Stack

Python 3.11+ · Pandas · OpenPyXL · FastAPI · Pydantic v2 · Streamlit

## Changelog

Release history is in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Bug reports and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md)
covers setup, testing and the PR process.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
