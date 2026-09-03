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

`docs/1_ProcessMaker_Bridges_Combined_Airtime_Report.csv` and `docs/Final_Report_11364-26082507344787.xlsx` are **not present** in this repo (lost, no backup found) — there is nothing to force-add for them currently. `src/tests/conftest.py::sample_csv_path` skips (rather than errors) tests that depend on the missing CSV. If either file is ever recovered, force-add it the same way and this note can be removed.

**Where it bites:** Any `git add .` or `git add docs/` will silently skip the `.xlsx` files above — they must always be force-added.

---

*Add new gotchas below as they're discovered.*