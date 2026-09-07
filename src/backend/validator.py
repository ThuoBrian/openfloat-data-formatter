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


def check_hard_errors(row: pd.Series, config: Settings) -> list[tuple[str, str]]:
    """Return (field, message) for each hard-error check the row fails.

    Shared by `validate()` (to build the validation report) and
    `transformer._build_output_rows()` (to decide which rows to skip), so the
    two can never drift apart on which rows count as invalid.
    """
    failures: list[tuple[str, str]] = []

    consent = str(row.get("consent", "")).strip()
    if consent.lower() != config.required_consent_value.lower():
        failures.append(
            ("consent", f"Consent is '{consent}', expected '{config.required_consent_value}'")
        )

    phone_raw = row.get("airtime_phone", "")
    _, phone_error = normalize_phone(phone_raw, config.default_country_prefix)
    if phone_error is not None:
        failures.append(("airtime_phone", phone_error))

    amount_raw = row.get("amount", 0)
    _, amount_error = normalize_amount(amount_raw)
    if amount_error is not None:
        failures.append(("amount", amount_error))

    network = str(row.get("network", "")).strip()
    _, network_error = map_network(network, config.network_map)
    if network_error is not None:
        failures.append(("network", network_error))

    return failures


# Maps a check_hard_errors() field name to its FilteredCounts attribute.
_FILTERED_COUNT_FIELD = {
    "consent": "consent_filtered",
    "airtime_phone": "invalid_phone",
    "amount": "invalid_amount",
    "network": "unmapped_network",
}
# Fields whose check_hard_errors() message gets a "Row N: " prefix (matches
# the original per-check message formatting).
_ROW_PREFIXED_FIELDS = {"airtime_phone", "amount", "network"}


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

        # --- Shared hard-error checks (consent, phone, amount, network) ---
        # Uses the same predicate transformer._build_output_rows() uses to
        # decide row exclusion, so the two can't drift apart.
        for field, message in check_hard_errors(row, config):
            full_message = f"Row {row_num}: {message}" if field in _ROW_PREFIXED_FIELDS else message
            row_errors.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.ERROR,
                    field=field,
                    message=full_message,
                )
            )
            count_field = _FILTERED_COUNT_FIELD[field]
            setattr(filtered_counts, count_field, getattr(filtered_counts, count_field) + 1)

        # --- Amount threshold (soft warning; only meaningful if amount itself is valid) ---
        amount_raw = row.get("amount", 0)
        amount_value, amount_error = normalize_amount(amount_raw)
        if amount_error is None and amount_value > config.max_amount_threshold:
            warnings.append(
                ValidationIssue(
                    row_number=row_num,
                    severity=IssueSeverity.WARNING,
                    field="amount",
                    message=f"Row {row_num}: Amount {amount_value} exceeds threshold {config.max_amount_threshold}",
                )
            )

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