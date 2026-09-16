# AGENTS.md

Guidance for AI coding agents (Copilot, Cursor, Claude, etc.) working in this
repository.

**Read [CLAUDE.md](CLAUDE.md) first** — it is the single, authoritative
agent-facing document for this repo: project summary, domain rules (phone
normalization, network mapping, statement reconciliation),
architecture, build & run commands (all uv-based), and the error-handling
convention (hard errors vs soft warnings).

Everything below is a summary; CLAUDE.md has the details.

## Commands

```bash
uv sync --python 3.12   # one-time setup (no venv activation, no PYTHONPATH)
uv run pytest -v        # run the test suite
uv run ruff check .     # lint (config in pyproject.toml; CI enforces)
uv run mypy             # type-check src + tests (CI enforces)
./start.sh ui           # Streamlit UI  → http://localhost:8501
./start.sh api          # FastAPI       → http://localhost:8000/docs
```

## Ground rules

- Never add `sys.path`/`PYTHONPATH` hacks — the package is installed editable.
- Imports use `openfloat_formatter.*` everywhere.
- `pyproject.toml` + `uv.lock` are the single dependency source (no
  requirements.txt).
- `sample_report_output/` contains real personal data — never `git add -f`
  it and never reference it from tests.
- Exactly two files in `docs/` are tracked, force-added past `.gitignore`:
  `openfloat-transactions-template.xlsx` and `processmaker-input-template.xlsx`.
  **Any other spreadsheet in `docs/` is real data** — a staff airtime export
  dropped there for manual testing carries names, staff IDs and phone numbers.
  Leave it untracked, never `git add -f` it, never read it into a terminal, and
  never reference it from tests.
- Check `docs/GOTCHA.md` before debugging surprising pandas/openpyxl behavior.
- Update `CLAUDE.md` when domain rules, architecture, or commands change.