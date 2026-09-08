# Contributing

## Getting set up

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ThuoBrian/openfloat-data-formatter.git
cd openfloat-data-formatter
uv sync --python 3.12
```

Confirm your setup works: `uv run pytest -v` should pass.

## Making a change

1. Branch from `main`: `git checkout -b <short-description>`.
2. Make the change. If it touches phone normalization, network mapping,
   consent filtering, amount validation, `case_remark` parsing, or statement
   reconciliation, read [CLAUDE.md](CLAUDE.md) first — those rules are
   deliberate and have edge cases.
3. Add or update tests for the change.
4. Run the checks below — all must pass; CI runs the same ones.
5. Commit with a clear, imperative message (e.g. `Fix phone normalization for
   012-prefixed numbers`) — see `git log` for the existing style.
6. Open a pull request using the repo's PR template
   (`.github/PULL_REQUEST_TEMPLATE.md` fills in automatically); it includes a
   checklist for the domain rules and error-handling convention.

## Code style

[Ruff](https://docs.astral.sh/ruff/) enforces linting (config in
`pyproject.toml`); there's no separate formatter step. Fix anything it flags
before opening a PR.

```bash
uv run ruff check .
```

## Type checking

```bash
uv run mypy
```

## Tests

```bash
uv run pytest -v                            # full suite
uv run pytest tests/test_normalizer.py -v   # one module
uv run pytest -k "test_phone" -v            # by name pattern
```

Tests live in `tests/`, one module per `src/openfloat_formatter/*.py` file.
Statement-report tests build synthetic workbooks
(`tests/conftest.py::make_statement_workbook`) rather than reading real
exports — `sample_report_output/` contains real personal data and must never
be referenced from a test or force-added to git.

## Review

This is currently a single-maintainer project (Brian Thuo); expect PRs to be
reviewed personally, not by a dedicated team. There's no fixed SLA — ping the
PR if it's been quiet a while.

## Reporting bugs

Open a GitHub issue with: what you ran (input file shape, mode used), what
you expected, what actually happened, and the exact error text if there was
one. Don't attach real beneficiary data (phone numbers, names) to an issue —
use the sample/template files in `docs/` or redact first.
