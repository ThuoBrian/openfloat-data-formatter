"""Core transformation pipeline for the OpenFloat Data Formatter.

Orchestrates the full pipeline: read → validate → normalize → map → build output.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from .config import Settings, settings
from .mapper import map_network
from .models import IssueSeverity, OutputRow, TransformResult, ValidationIssue
from .normalizer import format_case_remark, normalize_amount, normalize_phone, parse_case_remark
from .validator import validate
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
    output_rows, error_row_indices = _build_output_rows(df, config)

    # Update report with final valid count
    report.valid_rows = len(output_rows)

    # Step 4: Load Allowed Types from reference template
    allowed_types = load_allowed_types(config.openfloat_template_path)

    # Step 5: Write output Excel
    output_buffer = write_openfloat_excel(output_rows, allowed_types)

    return TransformResult(
        output=output_buffer,
        validation_report=report,
        output_row_count=len(output_rows),
    )


def _read_input(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(str(path))
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        return pd.read_excel(str(path))
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

    Skips rows where:
    - consent != "Yes" (case-insensitive)
    - Phone normalization fails
    - Network mapping fails
    - Amount validation fails

    Returns:
        A tuple of (output_rows, error_row_indices).
    """
    output_rows: list[OutputRow] = []
    error_indices: set[int] = set()

    for idx, row in df.iterrows():
        # --- Consent filter ---
        consent = str(row.get("consent", "")).strip()
        if consent.lower() != config.required_consent_value.lower():
            error_indices.add(idx)
            continue

        # --- Phone normalization ---
        phone_raw = row.get("airtime_phone", "")
        normalized_phone, phone_error = normalize_phone(
            phone_raw, config.default_country_prefix
        )
        if phone_error is not None:
            error_indices.add(idx)
            continue

        # --- Network mapping ---
        network = str(row.get("network", "")).strip()
        account_type, network_error = map_network(network, config.network_map)
        if network_error is not None:
            error_indices.add(idx)
            continue

        # --- Amount validation ---
        amount_raw = row.get("amount", 0)
        amount_value, amount_error = normalize_amount(amount_raw)
        if amount_error is not None:
            error_indices.add(idx)
            continue

        # --- Build Remark from case_remark (soft-falls back on parse failure) ---
        # Note: an empty CSV/Excel cell reads as NaN, not "", so check pd.isna
        # first — str(NaN) would otherwise become the literal string "nan".
        case_remark_cell = row.get("case_remark", "")
        case_remark_raw = "" if pd.isna(case_remark_cell) else str(case_remark_cell).strip()
        case_remark_parts, _ = parse_case_remark(case_remark_raw) if case_remark_raw else (None, None)
        if case_remark_parts is not None:
            remark = format_case_remark(case_remark_parts)
        elif case_remark_raw:
            # Doesn't match the expected pattern — keep the raw text rather than
            # silently dropping it (validator already raised a warning for this).
            remark = case_remark_raw
        else:
            project_name = str(row.get("project_name", "")).strip()
            project_activity = str(row.get("Project_Activity", "")).strip()
            remark = f"{project_name} - {project_activity}" if project_name or project_activity else ""

        # --- Create OutputRow ---
        output_rows.append(
            OutputRow(
                **{
                    "Account Type": account_type,
                    "Account Name": str(row.get("unique_id", "")),
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