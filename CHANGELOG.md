# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
  statement's own columns plus the file each came from, which is what tells them
  apart when several statements are uploaded at once.
- The identifier column feeding the output `Account Name` is now **detected
  from the headers** instead of being read from a fixed column name, so exports
  calling it `Staff ID`, `Staff`, `Respondent ID`, `respo` or `Beneficiary Ref`
  work with no configuration. The Transform page shows which column it picked,
  with sample values, and lets you override it per upload; `/transform` and
  `/validate` accept an `account_name_column` form field, and
  `ACCOUNT_NAME_COLUMN` sets it globally.

### Changed

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