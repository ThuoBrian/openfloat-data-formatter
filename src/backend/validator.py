"""Input validation for the OpenFloat Data Formatter.

Scans a Process Maker DataFrame and collects all issues before transformation.
Hard errors (consent, phone, network, amount) exclude rows from output.
Soft warnings (duplicates, high amounts) include rows but flag them.

Implements the validation rules from the golden prompt §4.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from .config import Settings, settings
from .mapper import map_network
from .models import FilteredCounts, IssueSeverity, ValidationIssue, ValidationReport
from .normalizer import normalize_amount, normalize_phone, resolve_case_remark


def validate(
    df: pd.DataFrame,
    config: Settings | None = None,
) -> ValidationReport:
    """Validate a Process Maker DataFrame and return a detailed report.

    This function scans every row and collects hard errors and soft warnings
    without modifying the DataFrame. Hard errors cause the row to be excluded
    from transformation; soft warnings are surfaced but the row is included.

    Args:
        df: The Process Maker DataFrame to validate.
        config: Optional settings override. Uses global defaults if None.

    Returns:
        A ValidationReport with row counts, filtered counts, errors, and warnings.
    """
    if config is None:
        config = settings

    total_rows = len(df)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    filtered_counts = FilteredCounts()

    # Track which rows have hard errors (will be excluded)
    rows_with_errors: set[int] = set()

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based, accounting for header row
        row_errors: list[ValidationIssue] = []

        # --- Consent filter (hard error) ---
        consent = str(row.get("consent", "")).strip()
        if consent.lower() != config.required_consent_value.lower():
            row_errors.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.ERROR,
                    field="consent",
                    message=f"Consent is '{consent}', expected '{config.required_consent_value}'",
                )
            )
            filtered_counts.consent_filtered += 1

        # --- Phone validation (hard error) ---
        phone_raw = row.get("airtime_phone", "")
        _, phone_error = normalize_phone(phone_raw, config.default_country_prefix)
        if phone_error is not None:
            row_errors.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.ERROR,
                    field="airtime_phone",
                    message=f"Row {row_num}: {phone_error}",
                )
            )
            filtered_counts.invalid_phone += 1

        # --- Amount validation (hard error for non-numeric/<=0, warning for >threshold) ---
        amount_raw = row.get("amount", 0)
        amount_value, amount_error = normalize_amount(amount_raw)
        if amount_error is not None:
            row_errors.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.ERROR,
                    field="amount",
                    message=f"Row {row_num}: {amount_error}",
                )
            )
            filtered_counts.invalid_amount += 1
        elif amount_value > config.max_amount_threshold:
            warnings.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.WARNING,
                    field="amount",
                    message=f"Row {row_num}: Amount {amount_value} exceeds threshold {config.max_amount_threshold}",
                )
            )

        # --- Network mapping (hard error for unmapped) ---
        network = str(row.get("network", "")).strip()
        _, network_error = map_network(network, config.network_map)
        if network_error is not None:
            row_errors.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.ERROR,
                    field="network",
                    message=f"Row {row_num}: {network_error}",
                )
            )
            filtered_counts.unmapped_network += 1

        # --- case_remark format check (soft warning, falls back to raw text) ---
        case_remark_raw, case_remark_parts, case_remark_error = resolve_case_remark(
            row.get("case_remark", "")
        )
        if case_remark_raw:
            if case_remark_error is not None:
                warnings.append(
                    ValidationIssue(
                        row_number=row_num,
                        severity=IssueSeverity.WARNING,
                        field="case_remark",
                        message=f"Row {row_num}: {case_remark_error} — using raw text as Remark",
                    )
                )
            elif amount_error is None and float(case_remark_parts.amount) != amount_value:
                warnings.append(
                    ValidationIssue(
                        row_number=row_num,
                        severity=IssueSeverity.WARNING,
                        field="case_remark",
                        message=(
                            f"Row {row_num}: case_remark amount (KSH {case_remark_parts.amount}) "
                            f"does not match the Amount column ({amount_value})"
                        ),
                    )
                )

        # Collect row errors
        for err in row_errors:
            errors.append(err)
            rows_with_errors.add(idx)

    # --- Duplicate phone detection (soft warning) ---
    phone_counts: Counter[str] = Counter()
    for idx, row in df.iterrows():
        phone_raw = str(row.get("airtime_phone", "")).strip()
        phone_key, _ = normalize_phone(phone_raw, config.default_country_prefix)
        if phone_key:  # Only count valid phones
            phone_counts[phone_key] += 1

    for phone, count in phone_counts.items():
        if count > 1:
            # Find all rows with this phone
            dup_rows = []
            for idx, row in df.iterrows():
                phone_raw = str(row.get("airtime_phone", "")).strip()
                normalized, _ = normalize_phone(phone_raw, config.default_country_prefix)
                if normalized == phone:
                    dup_rows.append(idx + 2)  # 1-based, accounting for header
            warnings.append(
                ValidationIssue(
                    row_number=dup_rows[0],
                    severity=IssueSeverity.WARNING,
                    field="airtime_phone",
                    message=f"Duplicate phone number {phone} appears on rows {', '.join(str(r) for r in dup_rows)}",
                )
            )

    valid_rows = total_rows - len(rows_with_errors)

    return ValidationReport(
        total_rows=total_rows,
        valid_rows=valid_rows,
        filtered_counts=filtered_counts,
        errors=errors,
        warnings=warnings,
    )