# GOTCHA.md

Lessons learned, pitfalls encountered, and non-obvious behaviors discovered during development.

---

## 1. Pandas int64 columns reject string assignment

**Problem:** Setting `df.loc[0, "amount"] = "abc"` on a column that pandas inferred as `int64` throws:
```
TypeError: Invalid value 'abc' for dtype 'int64'
```

**Fix:** Cast the column to `object` type before inserting non-numeric values:
```python
df["amount"] = df["amount"].astype(object)
df.loc[0, "amount"] = "abc"
```

**Where it bites:** Test fixtures that inject invalid amount strings into DataFrames loaded from CSV (where pandas infers `int64` for all-numeric columns).

---

## 2. Phone normalization edge case with `2540` prefix

**Problem:** Input `254012345678` — after stripping the `254` country prefix, you get `012345678` (9 digits starting with 0). Naively removing the leading zero would give `12345678` (only 8 digits), which fails validation.

**Fix:** The leading-zero removal step should only apply when the number has *more* than 9 digits after the country prefix is removed (i.e., the zero is an extra local dialing prefix like `0712345678`). If it's already exactly 9 digits, keep it as-is.

```python
# Correct logic:
if stripped.startswith("0") and len(stripped) > 9:
    stripped = stripped[1:]
```

**Where it bites:** Any phone number that starts with `0` after country code removal, common in Kenyan numbers like `012345678`.

---

## 3. OpenPyXL writes empty strings as `None`

**Problem:** When you write an empty string `""` to an openpyxl cell, reading it back returns `None` (null), not `""`.

```python
ws.cell(row=2, column=4).value = ""
assert ws.cell(row=2, column=4).value is None  # True!
```

**Fix:** Tests checking for empty optional fields should accept both `""` and `None`:
```python
assert cell.value in ("", None)
```

**Where it bites:** The `Till or Paybill Number` and `Till or Paybill Business Name` columns in the Accounts sheet are always empty for airtime disbursements.

---

## 4. Allowed Types count is 63, not 62

**Problem:** The golden prompt spec stated 62 allowed types, but the actual `openfloat-transactions-template.xlsx` has **63 entries** in the Allowed Types sheet. The first entry (`Mpesa`) is data, not a header row — the sheet has no header.

**Fix:** Always verify counts against the real template file. The `load_allowed_types()` function reads all non-None values from column A, which correctly returns 63 entries.

**Where it bites:** Any hardcoded count assumption. Use `len(load_allowed_types(template_path))` instead of a magic number.

---

## 5. `SPA NAKURU RURAL ` has a trailing space

**Problem:** The OpenFloat template entry `SPA NAKURU RURAL ` (note the trailing space) must be preserved exactly. If the writer trims whitespace, this entry would become `SPA NAKURU RURAL` (no trailing space), which would fail OpenFloat's upload validation.

**Fix:** The `load_allowed_types()` function uses `str(value)` on each cell without `.strip()`, preserving the exact string including trailing spaces. The writer then copies these verbatim into the output.

```python
# Correct — preserves trailing spaces:
types.append(str(value))

# Wrong — would lose the trailing space:
types.append(str(value).strip())
```

**Where it bites:** Any code that processes or compares Allowed Types entries. Never `.strip()` values from the template.

---

## 6. `.gitignore` excludes `*.csv` and `*.xlsx`

**Problem:** The `.gitignore` blocks CSV and Excel files, but `docs/` contains reference data files in both formats that must be tracked.

**Fix:** The `.xlsx` reference files that actually exist are force-added with `git add -f`:
```bash
git add -f docs/openfloat-transactions-template.xlsx
git add -f docs/processmaker-input-template.xlsx
```

`docs/1_ProcessMaker_Bridges_Combined_Airtime_Report.csv` and `docs/Final_Report_11364-26082507344787.xlsx` are **not present** in this repo (lost, no backup found) — there is nothing to force-add for them currently. `tests/conftest.py::sample_csv_path` skips (rather than errors) tests that depend on the missing CSV. If either file is ever recovered, force-add it the same way and this note can be removed.

**Where it bites:** Any `git add .` or `git add docs/` will silently skip the `.xlsx` files above — they must always be force-added.

---

## 7. The identifier column is detected, never hardcoded

**Problem:** Real exports name the Account Name source per run — `Staff ID`, `Respondent ID`, `Staff`, `respo`, `Beneficiary Ref`. Code that reads `row.get("unique_id", "")` finds nothing, and every row silently ships with a blank `Account Name`: no hard error, valid output file, unusable upload.

**Fix:** Resolve it through `normalizer.py::find_account_name_column(df.columns, config.account_name_column, frame=df)` — once per DataFrame, never per row — then read each row's cell with `resolve_unique_id`.

**Two near-misses the scoring exists to prevent**, both live in the same real file: `Staff Name ` sits next to `Staff ID` (a bare keyword match would pick the name), and our own `case_remark` contains the keyword `case`. Both are killed by the EXCLUDE pass, which rejects a header before scoring it. Add a keyword without checking it against a real header list and you can resurrect either.

**Where it bites:** `transformer.py` (Account Name), `validator.py` (the warnings) and `statement.py` (reconciliation entries) all resolve this — a new reader must use the same helper. Reading the tells in the UI:

- a warning on *every* row saying **no identifier column found** → nothing in the file looks like an ID; pick the column in the dropdown.
- a warning naming a column (**'Staff ID' is empty**) → detection worked, that row's cell is genuinely blank.
- **one** warning on row 1 about a *configured* column → a stale `ACCOUNT_NAME_COLUMN` in `.env`; it fell back to detection rather than blanking the file.

---

## 8. The Remark's amount is a case total, and only accepts whole digits

**Problem:** `AIRTIME-KSH(?P<amount>\d+)` takes **digits only**, while `normalize_amount` returns floats. Formatting a case total straight into the reference yields `AIRTIME-KSH28000.0`, which does not parse — and because composition falls back to the short `C#38305` on a failed self-check, the feature looks like it silently did nothing. `remark.py::_whole_kes` renders the integer, and refuses (keeping the short Remark and warning) only for a genuinely fractional total, using the same 0.01 tolerance `statement.py` uses so float noise from summing never trips it.

**Also:** that amount is the **per-case total**, not the row's amount. Two things follow. The validator cross-checks a typed amount against the case total, so a correctly-typed multi-row case no longer warns on every row. And the total covers the rows of *this upload* that survive `check_hard_errors` — split a case across two uploads and each carries a partial total, which `statement.py::rollup_by_case` will then flag as a difference. That is honest about what was uploaded; don't "fix" it.

**Where it bites:** `remark.py` (composition and the cross-check), `statement.py::rollup_by_case` (the other side of the round-trip).

---

## 9. `project_name` is not the project code

**Problem:** The identifier-column scorer (gotcha #7) must not be reused to find the project-code column: its exclude list contains `project` and its ID tokens contain `code`. And in a real export `project_name` is `AGRA Project` — a value with a space, which composes a reference that will not parse.

**Fix:** `remark.py::find_project_code_column` matches whole normalized headers against `config.PROJECT_CODE_COLUMNS`, so `project_name` and `Project_Activity` can never match; and every composed reference is round-tripped before use, so a spaced code degrades to a short Remark plus a warning rather than an unreadable reference.

---

*Add new gotchas below as they're discovered.*