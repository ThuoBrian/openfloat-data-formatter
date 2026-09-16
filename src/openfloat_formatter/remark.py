"""Building the output Remark column.

The Remark is the case reference finance reads, and it is the string OpenFloat
echoes back on its Transaction Statement export, where `statement.py` re-parses
it to roll payments up per case. Everything here ends in the same place: a
Remark `parse_case_remark` can read back, or none at all — a composed reference
is never written unless parsing it returns exactly the pieces it was built from.

Priority per row:

1. `case_remark` typed in full         -> used as typed (spacing canonicalized)
2. `case_remark` typed short (C#38305) -> composed into the full reference
3. `case_remark` present, unparseable  -> kept verbatim
4. no `case_remark`                    -> legacy "{project_name} - {Project_Activity}"

Only 2 composes; a reference someone typed in full is never rewritten.

`build_remark_context` is a pure function of (DataFrame, Settings, eligible
rows), so `validator.validate` and `transformer._build_output_rows` each build
their own and still agree — determinism, not shared state, is what keeps the
warnings in the report describing the Remark in the file.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

import pandas as pd

from .config import PROJECT_CODE_COLUMNS, Settings
from .normalizer import (
    CaseRemarkParts,
    _header_key,
    format_case_remark,
    normalize_amount,
    parse_case_remark,
    read_text_cell,
    resolve_case_remark,
)

# Input column carrying "<activity_code>|<activity_name>", e.g. "g06|Communications".
ACTIVITY_COLUMN = "Project_Activity"

# A case total this far off a whole number is float noise from summing; further
# off than this is a real fraction the reference format cannot express.
_WHOLE_KES_TOLERANCE = 0.01


class RemarkContext(NamedTuple):
    """Everything about one input file that the per-row Remark build needs."""

    case_totals: dict[str, float]
    project_code_column: str | None = None
    fallback_project_code: str = ""
    file_warnings: tuple[str, ...] = ()


class RemarkResult(NamedTuple):
    """One row's Remark, plus the soft warning (if any) that explains it."""

    remark: str
    warning: str | None = None
    field: str = "case_remark"


def find_project_code_column(columns: Iterable[object]) -> str | None:
    """Find the column holding the project code, whatever the export calls it.

    A plain tolerant alias match on the whole header (case, spaces, underscores
    and hyphens ignored) — deliberately not the fuzzy scoring used for the
    identifier column, whose exclude list contains 'project' and whose ID tokens
    contain 'code'. Matching whole keys is also what keeps `project_name` and
    `Project_Activity`, which sit beside it in every export, from ever matching.
    """
    aliases = {_header_key(name) for name in PROJECT_CODE_COLUMNS}
    for name in columns:
        if _header_key(name) in aliases:
            return str(name)
    return None


def case_totals(rows: Iterable[pd.Series]) -> dict[str, float]:
    """Total each case's amount across the rows given, keyed by case number.

    Callers pass only the rows that will reach the output, so a row excluded for
    a bad phone cannot inflate the figure finance reads. Keying on the *parsed*
    case number collapses `C# 38305` and `C#38305` into one case, and full-form
    rows are counted alongside short-form ones so a mixed file still totals once.
    """
    totals: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        _raw, parts, _error = resolve_case_remark(row.get("case_remark", ""))
        if parts is None:
            continue
        amount, amount_error = normalize_amount(row.get("amount", 0))
        if amount_error is None:
            totals[parts.case_number] += amount
    return dict(totals)


def _whole_kes(total: float) -> str | None:
    """Render a case total for `AIRTIME-KSH<amount>`, which only accepts digits.

    Returns None for a genuinely fractional total: rounding it would misstate the
    figure a case is reconciled against, so the Remark stays short instead.
    """
    nearest = round(total)
    return str(nearest) if abs(total - nearest) < _WHOLE_KES_TOLERANCE else None


def _is_usable_code(value: str) -> bool:
    """A reference field is whitespace-separated, so a code cannot contain spaces."""
    return bool(value) and not any(character.isspace() for character in value)


def _activity_code(row: pd.Series) -> str:
    """The code before the '|' in Project_Activity ('g06|Communications' -> 'g06')."""
    return read_text_cell(row.get(ACTIVITY_COLUMN, "")).split("|", 1)[0].strip()


def build_remark_context(
    df: pd.DataFrame,
    config: Settings,
    eligible_rows: Iterable[pd.Series],
) -> RemarkContext:
    """Gather the per-file inputs for composing Remarks, plus file-level warnings.

    Args:
        df: The whole input DataFrame (for its headers and its short-form count).
        config: Settings, for the fallback project code.
        eligible_rows: The rows that will reach the output — see `case_totals`.
    """
    totals = case_totals(eligible_rows)
    project_code_column = find_project_code_column(df.columns)
    fallback = (config.project_code or "").strip()

    warnings: list[str] = []
    short_form_rows = sum(
        1
        for _index, row in df.iterrows()
        if (parts := resolve_case_remark(row.get("case_remark", ""))[1]) is not None
        and parts.amount is None
    )
    if short_form_rows and fallback and not _is_usable_code(fallback):
        # Whatever the rows say, one bad configured code is one problem.
        warnings.append(
            f"project code '{fallback}' cannot be used in a case reference (it contains "
            f"spaces), so those rows keep a short Remark"
        )
    if short_form_rows and project_code_column is None and not fallback:
        # File-level, not per row: one line, not one per row, matching how a
        # stale ACCOUNT_NAME_COLUMN is reported.
        warnings.append(
            f"{short_form_rows} row(s) carry a short case reference (C#...) that cannot be "
            f"completed: no project code available. Add a project_code column to the export, "
            f"or set the project code in the app"
        )
    for case_number, total in sorted(totals.items()):
        if _whole_kes(total) is None:
            warnings.append(
                f"case {case_number} totals {total:,.2f}, which is not a whole number of KES "
                f"and cannot go in a case reference — those rows keep a short Remark"
            )

    return RemarkContext(
        case_totals=totals,
        project_code_column=project_code_column,
        fallback_project_code=fallback,
        file_warnings=tuple(warnings),
    )


def build_remark(row: pd.Series, context: RemarkContext) -> RemarkResult:
    """Build one row's Remark, with the soft warning that explains any shortfall."""
    raw, parts, _error = resolve_case_remark(row.get("case_remark", ""))
    if parts is None:
        # Unparseable text is kept verbatim rather than dropped; validate()
        # warns about the parse failure itself.
        return RemarkResult(raw if raw else _legacy_remark(row))

    if parts.amount is not None:
        return _check_typed_amount(parts, context)
    return _compose(row, parts, context)


def _check_typed_amount(parts: CaseRemarkParts, context: RemarkContext) -> RemarkResult:
    """A full-form reference is used as typed; its amount is cross-checked.

    The embedded amount is the per-case total, so it is compared against the
    total of the case's rows — not against one row's own amount, which would
    warn on every row of a correctly-typed multi-row case.
    """
    remark = format_case_remark(parts)
    total = context.case_totals.get(parts.case_number)
    if (
        parts.amount is not None
        and total is not None
        and abs(float(parts.amount) - total) >= _WHOLE_KES_TOLERANCE
    ):
        return RemarkResult(
            remark,
            f"case_remark amount (KSH {parts.amount}) does not match the case total "
            f"({total:,.0f}) across this file's rows",
        )
    return RemarkResult(remark)


def _compose(
    row: pd.Series,
    parts: CaseRemarkParts,
    context: RemarkContext,
) -> RemarkResult:
    """Build the full reference around a short `C#<case_number>` remark."""
    short = format_case_remark(parts)

    project_code, from_column = _project_code(row, context)
    if not project_code:
        if context.project_code_column is None and not context.fallback_project_code:
            # Already said once, file-level, by build_remark_context.
            return RemarkResult(short)
        return RemarkResult(
            short,
            f"'{context.project_code_column}' is empty and no fallback project code is set, "
            f"so the case reference stays short",
            "project_code",
        )

    activity_code = _activity_code(row)
    if not activity_code:
        return RemarkResult(
            short,
            f"'{ACTIVITY_COLUMN}' is empty, so there is no activity code and the case "
            f"reference stays short",
        )

    total = context.case_totals.get(parts.case_number)
    if not total:
        # Reachable inside validate(), which sees rows excluded from the totals.
        return RemarkResult(short)
    amount = _whole_kes(total)
    if amount is None:
        return RemarkResult(short)  # said once, file-level

    composed_parts = CaseRemarkParts(parts.case_number, project_code, amount, activity_code)
    composed = format_case_remark(composed_parts)
    if parse_case_remark(composed)[0] != composed_parts:
        # Self-check: a code containing a space would produce a reference that
        # silently fails to parse when OpenFloat echoes it back. A bad *configured*
        # code is already reported once, file-level; only a row's own column value
        # is worth saying per row.
        if not from_column:
            return RemarkResult(short)
        return RemarkResult(
            short,
            f"composed case reference '{composed}' cannot be read back (a project or "
            f"activity code cannot contain spaces), so it stays short",
            "project_code",
        )
    return RemarkResult(composed)


def _project_code(row: pd.Series, context: RemarkContext) -> tuple[str, bool]:
    """This row's project code and whether it came from the file's own column.

    A code from the row's column is row-specific, so a problem with it is worth
    a per-row warning; the configured fallback is reported once, file-level.
    """
    if context.project_code_column is not None:
        from_column = read_text_cell(row.get(context.project_code_column, ""))
        if from_column:
            return from_column, True
    return context.fallback_project_code, False


def _legacy_remark(row: pd.Series) -> str:
    """Pre-case_remark fallback, for exports carrying no reference at all."""
    parts = [
        read_text_cell(row.get("project_name", "")),
        read_text_cell(row.get(ACTIVITY_COLUMN, "")),
    ]
    # Joining only what is filled avoids a dangling " - " when one side is blank.
    return " - ".join(part for part in parts if part)
