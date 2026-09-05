# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Adopted ruff (lint) and mypy (type checking) as dev tooling; both run in CI
  alongside pytest. Config lives in `pyproject.toml`.
- Modernized a few patterns surfaced by the linters: `IssueSeverity` is a
  `StrEnum`, FastAPI endpoints use the `Annotated` style, `zip()` calls pass
  `strict=`, and `write_openfloat_excel` gained typed `@overload`s.
- Filled in `pyproject.toml` metadata (authors, license, URLs, classifiers)
  and added `__version__` to the package.

### Fixed

- Documentation: stale pre-src-layout paths in the PR template,
  `sample_report_output/README.md`, and `CLAUDE.md`; removed the hardcoded
  test count. Added a proprietary License & use section and an HTTP API table
  to the README, a thin `AGENTS.md` for coding agents, and this changelog.

## [0.1.0] — 2026-08-25

Initial release: Process Maker → OpenFloat transform pipeline, validation
reporting, Streamlit UI (Transform + Statement Report modes), FastAPI
endpoints, and a pytest suite.