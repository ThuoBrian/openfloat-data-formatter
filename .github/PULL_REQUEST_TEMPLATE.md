# Pull Request

## Summary

<!-- What does this PR change and why? Link any related issue. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Docs / reference data
- [ ] Tests only
- [ ] Other:

## Domain rules touched

<!-- Check any that this PR affects, so reviewers know which CLAUDE.md rules to double-check. -->

- [ ] Phone normalization
- [ ] Network → Account Type mapping
- [ ] Consent filter
- [ ] Duplicate detection
- [ ] Amount validation
- [ ] `case_remark` / Remark parsing
- [ ] Output writer (Excel formatting, sanitization, Allowed Types sheet)
- [ ] None of the above

## Error handling convention

<!-- If validation logic changed, confirm the hard-error / soft-warning split still holds. -->

- [ ] Hard errors (invalid phone, unmapped network, invalid amount, non-`Yes` consent) still exclude the row and are reported in `errors`
- [ ] Soft warnings (duplicates, high amounts, `case_remark` parse/mismatch) still include the row and are reported in `warnings`
- [ ] Validator still never mutates the input DataFrame
- [ ] N/A — no validation logic changed

## How was this tested?

```bash
uv run ruff check .
uv run mypy
uv run pytest -v
```

<!-- (Set up first with `uv sync --python 3.12` if you haven't. Paste relevant
output below, or describe manual verification — e.g. ran through the Streamlit
UI, sample file used.) -->

- [ ] Added/updated tests for this change
- [ ] `ruff check`, `mypy`, and all tests pass locally
- [ ] Ran manually against sample data in `docs/`

## Checklist

- [ ] Free-text values written to output (Remark, Account Name) are sanitized against formula injection, if applicable
- [ ] `CLAUDE.md` updated if domain rules, architecture, or commands changed
- [ ] No real PII (phone numbers, names) added to tracked files or pasted into commit messages/PR description — see IPA AI/data classification guidelines
