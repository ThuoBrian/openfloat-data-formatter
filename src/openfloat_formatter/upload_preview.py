"""What an upload will look like, worked out before anything is built.

The staff UI shows these beside the column pickers: which column each field
was read from, what the identifier column holds, and the Remark row 1 will
get. They live here rather than in a UI so the Streamlit page and the HTTP
API (and through it the React app) give the same answers while both exist.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .config import Settings
from .models import UploadPreview
from .normalizer import (
    canonicalize_input_columns,
    find_account_name_column,
    parse_case_remark,
    read_text_cell,
    resolve_input_columns,
)
from .remark import build_remark, count_short_form_rows, find_project_code_column
from .validator import remark_context

# The fields worth letting a user map by hand, with the plain-English label
# shown in the picker. Only these three fail every row when missing; the rest
# degrade gracefully, so cluttering the form with them would cost more than
# it gives.
MAPPABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("airtime_phone", "Phone number"),
    ("network", "Network / provider"),
    ("amount", "Amount"),
)

PREVIEW_ROW_COUNT = 10
IDENTIFIER_SAMPLE_COUNT = 3


def mapping_warnings(
    columns: pd.Index,
    chosen: Mapping[str, str],
    detected: Mapping[str, str],
) -> list[str]:
    """Detection warnings for the guesses still standing after the user's picks.

    A column the user has already corrected should not keep warning about the
    original guess, so only the picks that differ from detection count as
    overrides here.
    """
    corrected = {
        field: column for field, column in chosen.items() if column != detected.get(field)
    }
    _, warnings = resolve_input_columns(columns, corrected)
    return warnings


def identifier_summary(raw_df: pd.DataFrame, column: str) -> tuple[int, list[str]]:
    """How many rows have an identifier, plus a few sample values.

    Sample values are the only way to catch a plausible-but-wrong identifier:
    a column can score well and still hold the wrong thing.
    """
    filled = [value for value in (read_text_cell(cell) for cell in raw_df[column]) if value]
    return len(filled), filled[:IDENTIFIER_SAMPLE_COUNT]


def remark_preview(df: pd.DataFrame, config: Settings) -> tuple[str | None, bool]:
    """The Remark row 1 will actually get, and whether a statement can read it back."""
    if df.empty:
        return None, False
    result = build_remark(df.iloc[0], remark_context(df, config))
    if not result.remark:
        return None, False
    return result.remark, parse_case_remark(result.remark)[1] is None


def describe_upload(
    raw_df: pd.DataFrame,
    config: Settings,
    overrides: Mapping[str, str] | None = None,
) -> UploadPreview:
    """Everything the column-mapping step shows, for one file and one set of picks.

    Args:
        raw_df: The input as read, with the file's own headers.
        config: Settings for this upload; `account_name_column` is the
            identifier the user picked (None = detect).
        overrides: Canonical field → the column the user picked for it.
    """
    columns = raw_df.columns
    detected, _ = resolve_input_columns(columns)
    mapping, _ = resolve_input_columns(columns, overrides)
    df = canonicalize_input_columns(raw_df, overrides)

    identifier = find_account_name_column(
        columns, override=config.account_name_column, frame=raw_df
    )
    filled, samples = identifier_summary(raw_df, identifier) if identifier else (0, [])
    remark, readable = remark_preview(df, config)
    head = df.head(PREVIEW_ROW_COUNT)

    return UploadPreview(
        columns=[str(column) for column in columns],
        row_count=len(raw_df),
        detected=detected,
        mapping=mapping,
        missing_fields=[field for field, _label in MAPPABLE_FIELDS if field not in mapping],
        # The raw picks, not `mapping`: a pick naming a column the file lacks
        # never reaches `mapping`, and its fallback warning must still show.
        mapping_warnings=mapping_warnings(columns, overrides or {}, detected),
        identifier_column=identifier,
        identifier_filled=filled,
        identifier_samples=samples,
        preview_columns=[str(column) for column in head.columns],
        preview_rows=[
            [read_text_cell(cell) for cell in row] for row in head.itertuples(index=False)
        ],
        short_form_rows=count_short_form_rows(df),
        project_code_column=find_project_code_column(df.columns),
        remark_preview=remark,
        remark_readable=readable,
    )
