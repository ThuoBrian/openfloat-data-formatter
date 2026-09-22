"""Core transformation pipeline for the OpenFloat Data Formatter.

Orchestrates the full pipeline: read → validate → normalize → map → build output.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Settings, settings
from .mapper import map_network
from .models import OutputRow, TransformResult
from .normalizer import (
    canonicalize_input_columns,
    find_account_name_column,
    normalize_amount,
    normalize_phone,
    read_text_cell,
)
from .remark import build_remark
from .validator import check_hard_errors, remark_context, validate
from .writer import load_allowed_types, write_openfloat_excel


def transform(
    input_path: str | Path,
    config: Settings | None = None,
) -> TransformResult:
    """Run the full transformation pipeline.

    1. Read the input file (CSV or Excel)
    2. Validate the data
    3. Filter and transform valid rows
    4. Write the output Excel file

    Args:
        input_path: Path to the Process Maker CSV or Excel file.
        config: Optional settings override. Uses global defaults if None.

    Returns:
        A TransformResult containing the output BytesIO, validation report,
        and row counts.
    """
    if config is None:
        config = settings

    input_path = Path(input_path)

    # Step 1: Read input file
    df = _read_input(input_path)

    # Step 2: Validate
    report = validate(df, config)

    # Step 3: Build output rows (skip rows with hard errors)
    output_rows, _error_row_indices = _build_output_rows(df, config)

    # Update report with final valid count
    report.valid_rows = len(output_rows)

    # Step 4: Load Allowed Types from reference template
    allowed_types = load_allowed_types(config.openfloat_template_path)

    # Step 5: Write output Excel — when every row was filtered out there is
    # nothing to upload, so signal that with output=None rather than shipping
    # an empty Accounts sheet (the API's 422 and the UI's "no output" branch
    # both rely on this).
    output_buffer = write_openfloat_excel(output_rows, allowed_types) if output_rows else None

    return TransformResult(
        output=output_buffer,
        validation_report=report,
        output_row_count=len(output_rows),
    )


def _read_input(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame.

    Column names are canonicalized on the way out, so an export calling its
    phone column 'payphone_number' reads the same as one calling it
    'airtime_phone'.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return canonicalize_input_columns(pd.read_csv(str(path)))
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        return canonicalize_input_columns(pd.read_excel(str(path)))
    else:
        raise ValueError(
            f"Unsupported file format: '{suffix}'. "
            f"Expected .csv, .xlsx, .xls, or .xlsm."
        )


def _build_output_rows(
    df: pd.DataFrame,
    config: Settings,
) -> tuple[list[OutputRow], set[int]]:
    """Transform valid rows into OutputRow objects.

    Skips rows that fail any of `validator.check_hard_errors()`'s checks
    (phone, network, amount) — the same predicate `validate()` uses
    to build the validation report, so the two can't drift apart.

    Returns:
        A tuple of (output_rows, error_row_indices).
    """
    output_rows: list[OutputRow] = []
    error_indices: set[int] = set()

    # Resolved once so every row draws its Account Name from the same column.
    id_column = find_account_name_column(df.columns, config.account_name_column, frame=df)
    # The same context validate() reports on, so warnings describe what is written.
    remarks = remark_context(df, config)

    for idx, row in df.iterrows():
        if check_hard_errors(row, config):
            error_indices.add(idx)
            continue

        normalized_phone, _ = normalize_phone(
            row.get("airtime_phone", ""), config.default_country_prefix
        )
        network = str(row.get("network", "")).strip()
        account_type, _ = map_network(network, config.network_map)
        amount_value, _ = normalize_amount(row.get("amount", 0))

        # --- Build Remark (composes the full case reference where it can) ---
        remark = build_remark(row, remarks).remark

        # --- Create OutputRow ---
        output_rows.append(
            OutputRow(
                **{
                    "Account Type": account_type,
                    "Account Name": (
                        read_text_cell(row.get(id_column, "")) if id_column else ""
                    ),
                    "Account Number": normalized_phone,
                    "Till or Paybill Number": "",
                    "Till or Paybill Business Name": "",
                    "Notification Phone Number": normalized_phone,
                    "Amount": amount_value,
                    "Remark": remark,
                }
            )
        )

    return output_rows, error_indices
