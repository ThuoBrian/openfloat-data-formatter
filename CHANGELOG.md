# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Clear error when this app's own report is uploaded as a statement.** A
  Statement Report or Finance download fed back into Statement Report mode used
  to fail with a generic "no 'Transaction Statement' sheet" message. It now
  says the file is a report from this app and asks for the original OpenFloat
  export.
- **Statement Report is the project leads' copy, in the statement's own
  columns.** Its Successful and Unsuccessful sheets now carry `Approval Id`
  through `Approved/Rejected By`, then `Amount`, then `Reference Id` (so a
  reversal still points at the original payment), replacing `Source File`,
  `Row` and `Status`. The download is named after the Remark, ending in
  `_report.xlsx`.
- **Finance sheet carries the full statement columns.** The Finance
  Reconciliation download now has `Approval Id`, `Transaction Id`,
  `Transaction Type`, `Transaction Status`, `Date`, `Account Name`,
  `Account Number`, `Account Type`, `Remark`, `Initiated By`,
  `Approved/Rejected By`, `Amount`, `Commission Amount`, `Debit`, `Credit` and
  `Balance After`, replacing the short `Phone`/`Case`/`Status` layout.
  `Commission Amount`, `Credit` and `Balance After` are copied from the
  statement when the export has them and left blank when it doesn't. The TOTAL
  is still under Debit only. The download is now named after the Remark (or
  the case numbers joined, `C#37154_C#37181`, when there are several cases).
- **Desktop and Start menu shortcuts.** The installer now adds an "OpenFloat
  Data Formatter" shortcut in both places, so staff start the app with a
  double-click instead of finding `run.bat` among the code files. Rerunning the
  installer to update overwrites the shortcuts, and a shortcut that can't be
  created never fails the install.

- **Input columns are matched by name, not by exact spelling.** Only the
  identifier column was flexible before; an export calling its phone column
  `payphone_number` or its network column `service_provider` failed every row
  against a column that was not there. `airtime_phone`, `network`, `amount`,
  `case_remark`, `project_name` and `Project_Activity` now each resolve
  through an alias table (`INPUT_COLUMN_ALIASES`), tolerant of case, spaces,
  underscores and hyphens, with a token fallback for the three fields whose
  absence fails every row. Because no alias table can cover every export, the
  Transform page also carries a **Column mapping** picker: it pre-selects what
  was detected — so a recognised file needs no interaction — and lets you point
  at any column yourself when the guess is wrong or the header is one nobody
  has seen before. It opens automatically when a required column is missing.
  The identifier column picker now lives in that same panel rather than its own
  always-visible section — same decision, one place — and still shows the fill
  count and sample values that catch a plausible-but-wrong guess.
- `Airtel Kenya` maps to `Airtel Prepaid`, for exports that write the carrier's
  full name.
- **Finance reconciliation download.** A second button on the Statement Report
  page produces the sheet finance posts from: every transaction in statement
  order with a `Debit` column, and one bold `TOTAL` under it. Debit is filled
  only for successful payments — not merely for rows that carry an amount — so
  the total is the money that actually left the float; failed and reversed rows
  are shaded and left with an empty Debit rather than dropped.
- **Statement Report downloads as an Excel workbook.** A `Successful` sheet and
  an `Unsuccessful` sheet (where Reversed rows land, with a blank Amount), plus
  a sheet per reconciliation bucket when a Process Maker input was uploaded.
  Every sheet ends in a bold `TOTAL` row over its amount columns. Rows carry the
  statement's own columns.
- The identifier column feeding the output `Account Name` is now **detected
  from the headers** instead of being read from a fixed column name, so exports
  calling it `Staff ID`, `Staff`, `Respondent ID`, `respo` or `Beneficiary Ref`
  work with no configuration. The Transform page shows which column it picked,
  with sample values, and lets you override it per upload; `/transform` and
  `/validate` accept an `account_name_column` form field, and
  `ACCOUNT_NAME_COLUMN` sets it globally.

### Changed

- **A `justfile` replaces `start.bat` and `start.sh`.** Developer commands are
  now `just ui`, `just api`, `just both`, `just test` and `just check` (the same
  lint, type-check and test gates CI runs). `just both` runs both servers in one
  terminal on every OS, and Ctrl+C stops both. Servers still bind to
  `127.0.0.1`. Staff are unaffected: `run.bat` and the installer are unchanged.

- A short `C#<case_number>` reference is now **composed into the full Remark**
  — `C#38305 22505AA RESP AIRTIME-KSH28000 g06` — using a `project_code`
  column (or the new `PROJECT_CODE` setting / Project Code box in the app), the
  activity code from `Project_Activity`, and the case's total across the upload.
  A reference typed in full is never rewritten, and a reference that cannot be
  read back is never written: the Remark stays short with a warning instead.
- **Fixed:** the `case_remark` amount cross-check compared the embedded amount
  against the row's own amount, but that amount is the per-case total — a
  correctly-typed reference on a multi-row case warned on every row. It now
  compares against the case total across the file.
- `case_remark` now also accepts the short `C#<case_number>` form (e.g.
  `C# 38305`), with an optional space after `C#` in both forms. It previously
  failed to parse, which meant a soft warning on every row and a Remark that
  the statement report could not roll up per case. A short remark carries no
  project code, amount or activity code, so those cases report no
  `remark_amount`/`difference` — the rows still group and total. A partially
  typed full form is still a parse error.
- **Behaviour change:** files whose identifier column was previously
  unrecognized (anything outside `unique_id`/`staff_id`/`respondent_id`/
  `case_id`/`reso_id`) shipped with a blank `Account Name` on every row; they
  now populate it. Columns whose name contains `Name`, `Phone`, `Amount` or
  `Remark` are never chosen as the identifier.
- Validation now distinguishes "no identifier column in this file" from "this
  row's identifier cell is blank", and reports a stale `ACCOUNT_NAME_COLUMN`
  once per file instead of once per row.

- Relicensed from proprietary/all-rights-reserved to
  [Apache License 2.0](LICENSE). `pyproject.toml`'s `license` field and
  classifiers updated to match; README's License section now points at
  `LICENSE`. Added `CONTRIBUTING.md`.
- README: added a CI status badge, a "Configuration" section documenting the
  `.env` settings, and a "Limitations" section; GUIDE.md gained a matching
  plain-language "What This App Doesn't Do" section.
- Adopted ruff (lint) and mypy (type checking) as dev tooling; both run in CI
  alongside pytest. Config lives in `pyproject.toml`.
- Modernized a few patterns surfaced by the linters: `IssueSeverity` is a
  `StrEnum`, FastAPI endpoints use the `Annotated` style, `zip()` calls pass
  `strict=`, and `write_openfloat_excel` gained typed `@overload`s.
- Filled in `pyproject.toml` metadata (authors, license, URLs, classifiers)
  and added `__version__` to the package.

### Fixed

- **`.xls` uploads work.** They were accepted everywhere but always failed,
  because pandas needs `xlrd` to read the old Excel format and it was not
  installed. `xlrd` is now a dependency.
- **The country prefix is checked.** A blank or mistyped prefix (`+254`, `25a`)
  silently rewrote every phone number in the batch. The app now stops with an
  error in the sidebar until it is 1 to 3 digits, and `DEFAULT_COUNTRY_PREFIX`
  in `.env` is held to the same rule.
- **The API refuses uploads over 20 MB** with a 413, rather than parsing them
  into memory. Statement files are covered too.
- **The API no longer sends CORS headers.** Nothing calls it from a browser,
  and the old wildcard origin let any web page post files to it on localhost.
- The sidebar shows one **Advanced settings** section instead of two; the
  amount threshold appears in it only in Transform mode.
- Dropped the deprecated `use_container_width` argument (Streamlit's default
  width already stretches), which silences the deprecation warnings.

- **A blank amount is now a hard error.** An empty cell reads as `NaN`, and
  `NaN <= 0` is false, so the row passed validation and went into the
  OpenFloat upload with an empty Amount. `nan`/`inf` typed as text were
  accepted the same way. All are now rejected; reconciliation also stops a
  blank input amount from hiding an amount mismatch.
- **Identifiers reach Account Name as typed.** Input files are now read with
  every cell as text (`transformer.read_input_file`, shared by the app, the API
  and `transform`). Inferred as numbers, `00123` lost its leading zeros, and one
  blank cell in the column made every ID go out as `123.0`.
- **Duplicate phones are reported even when a phone cell is blank.** The check
  stringified float cells into `712345678.0`, which never normalized, so one
  blank phone hid every duplicate in the file.
- The API returns 400, not 500, for an upload pandas cannot parse.
- **A blank phone cell no longer aborts the whole upload.** One empty
  `airtime_phone` makes pandas type the column `float64`, and converting the
  resulting `NaN` raised rather than returning an error — a single blank cell
  killed a 196-row file. The row is now an ordinary hard error and every other
  row still transforms.
- Documentation: stale pre-src-layout paths in the PR template,
  `sample_report_output/README.md`, and `CLAUDE.md`; removed the hardcoded
  test count. Added a proprietary License & use section and an HTTP API table
  to the README, a thin `AGENTS.md` for coding agents, and this changelog.

## [0.1.0] — 2026-08-25

Initial release: Process Maker → OpenFloat transform pipeline, validation
reporting, Streamlit UI (Transform + Statement Report modes), FastAPI
endpoints, and a pytest suite.