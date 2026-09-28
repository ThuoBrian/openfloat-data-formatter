# Contributing

## Getting set up

Requires [uv](https://docs.astral.sh/uv/). The commands below use
[just](https://just.systems/) (`winget install Casey.Just`, `brew install just`,
or `uv tool install rust-just`); each recipe is a thin wrapper over `uv run ...`,
listed in the [justfile](justfile) if you'd rather call uv directly.

```bash
git clone https://github.com/ThuoBrian/openfloat-data-formatter.git
cd openfloat-data-formatter
just sync
```

Confirm your setup works: `just test` should pass.

## Making a change

1. Branch from `main`: `git checkout -b <short-description>`.
2. Make the change. If it touches phone normalization, network mapping,
   amount validation, `case_remark` parsing, or statement
   reconciliation, read [AGENTS.md](AGENTS.md) first — those rules are
   deliberate and have edge cases.
3. Add or update tests for the change.
4. Run `just check` — lint, type-check and tests must all pass; CI runs the same ones.
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
just lint
```

## Type checking

```bash
just typecheck
```

## Tests

```bash
just test                              # full suite
just test tests/test_normalizer.py     # one module
just test -k test_phone                # by name pattern
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
