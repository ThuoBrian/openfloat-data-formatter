# sample_report_output/

Holds real **OpenFloat "Transaction Statement"** exports — the reports the
OpenFloat SaaS produces *after* staff upload a disbursement batch. They are
used to manually exercise the app's **Statement Report** mode (see
`src/openfloat_formatter/ui/app.py` and `src/openfloat_formatter/statement.py`).

## ⚠️ These files are NOT tracked by git

The exports in this directory contain **real personal data** — beneficiary
phone numbers and staff names — and `.gitignore` excludes `*.xlsx`. Do
**not** force-add them (`git add -f`). This README is tracked only so the
directory (and this warning) survives a fresh clone.

## Statement format reference

Parsing is implemented in
`src/openfloat_formatter/statement.py::parse_statement_file`
and tested with synthetic workbooks (`tests/conftest.py::
make_statement_workbook`) — the tests never read these real files.

Format facts:

- Single sheet named `Transaction Statement`
- Header-driven parsing: column count **varies** between exports (12 or 13
  columns — `Reference Id` is present only in some), and `Amount` is always
  the last column
- One row per disbursement; `Transaction Status` values seen in practice:
  `Successful` (carries an Amount) and `Reversed` (Amount empty, with a
  `Reference Id` pointing at the original transaction)
- A final **footer row** holds only the grand-total Amount
- `Remark` holds the case reference in the raw `case_remark` format
  (`C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>`)