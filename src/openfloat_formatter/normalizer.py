"""Phone number and field normalization for the OpenFloat Data Formatter.

Handles the normalization pipeline defined in the golden prompt §4.2:
1. Strip whitespace and special characters (-, (, ), +)
2. Remove 254 or 0 prefix → keep remaining 9 digits
3. Prepend country code for output
4. Reject numbers not exactly 9 digits after stripping
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

import pandas as pd


def normalize_phone(
    raw: str | int | float,
    country_prefix: str = "254",
) -> tuple[str, str | None]:
    """Normalize a phone number to international format.

    Args:
        raw: The raw phone number from Process Maker (string, int, or float).
        country_prefix: The country code to prepend (default "254" for Kenya).

    Returns:
        A tuple of (normalized_phone, error_message).
        On success: ("254XXXXXXXXX", None)
        On failure: ("", error_description)

    Examples:
        >>> normalize_phone("785271309")
        ('254785271309', None)
        >>> normalize_phone("254785271309")
        ('254785271309', None)
        >>> normalize_phone("0785271309")
        ('254785271309', None)
        >>> normalize_phone("123")
        ('', "Phone number '123' is not 9 digits after stripping prefixes")
    """
    # Convert to string if numeric
    raw_str = str(int(raw)) if isinstance(raw, float) else str(raw)

    # Step 1: Strip whitespace and special characters: -, (, ), +
    stripped = re.sub(r"[\s\-\(\)\+]", "", raw_str)

    # Step 2: Remove country code prefix if present
    if stripped.startswith(country_prefix):
        stripped = stripped[len(country_prefix) :]

    # Step 3: Remove leading zero if present AND the result would still be >= 9 digits.
    # This handles numbers like "0712345678" (local format) but preserves
    # numbers like "012345678" which are already 9 digits after country code removal.
    if stripped.startswith("0") and len(stripped) > 9:
        stripped = stripped[1:]

    # Step 4: Validate — must be exactly 9 digits
    if not stripped.isdigit() or len(stripped) != 9:
        return (
            "",
            f"Phone number '{raw_str}' is not 9 digits after stripping prefixes",
        )

    # Step 5: Prepend country prefix for output
    normalized = f"{country_prefix}{stripped}"
    return (normalized, None)


def normalize_amount(raw: str | int | float) -> tuple[float, str | None]:
    """Coerce an amount value to a positive float.

    Args:
        raw: The raw amount from Process Maker.

    Returns:
        A tuple of (amount, error_message).
        On success: (150.0, None)
        On failure: (0.0, error_description)

    Examples:
        >>> normalize_amount("150")
        (150.0, None)
        >>> normalize_amount(150)
        (150.0, None)
        >>> normalize_amount("abc")
        (0.0, "Amount 'abc' is not numeric")
        >>> normalize_amount(-50)
        (0.0, "Amount -50 is not positive")
    """
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return (0.0, f"Amount '{raw}' is not numeric")

    if value <= 0:
        return (0.0, f"Amount {raw} is not positive")

    return (value, None)


# ---------------------------------------------------------------------------
# case_remark parsing
# ---------------------------------------------------------------------------

# Manually-typed case reference, fixed order, space-separated:
#   C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>
# Example: "C#37166 22505AA RESP AIRTIME-KSH29400 d05"
_CASE_REMARK_PATTERN = re.compile(
    r"^C#(?P<case_number>\d+)\s+(?P<project_code>\S+)\s+RESP\s+"
    r"AIRTIME-KSH(?P<amount>\d+)\s+(?P<activity_code>\S+)$"
)


class CaseRemarkParts(NamedTuple):
    """Structured pieces parsed out of a manually-typed `case_remark` string."""

    case_number: str
    project_code: str
    amount: str
    activity_code: str


def parse_case_remark(raw: str) -> tuple[CaseRemarkParts | None, str | None]:
    """Parse a manually-typed `case_remark` string into its component pieces.

    Expected format (fixed order, space-separated):
        C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>

    Args:
        raw: The raw case_remark value entered by the user.

    Returns:
        A tuple of (parts, error_message).
        On success: (CaseRemarkParts(...), None)
        On failure: (None, error_description)

    Examples:
        >>> parse_case_remark("C#37166 22505AA RESP AIRTIME-KSH29400 d05")
        (CaseRemarkParts(case_number='37166', project_code='22505AA', amount='29400', activity_code='d05'), None)
        >>> parse_case_remark("garbage")[0] is None
        True
    """
    match = _CASE_REMARK_PATTERN.match(raw.strip())
    if match is None:
        return (
            None,
            f"case_remark '{raw}' does not match expected format "
            f"'C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>'",
        )

    return (
        CaseRemarkParts(
            case_number=match.group("case_number"),
            project_code=match.group("project_code"),
            amount=match.group("amount"),
            activity_code=match.group("activity_code"),
        ),
        None,
    )


def resolve_case_remark(cell: Any) -> tuple[str, CaseRemarkParts | None, str | None]:
    """Resolve a raw `case_remark` DataFrame cell and parse it in one step.

    Centralizes the pandas NaN-guard + parse_case_remark call so validator.py
    and transformer.py can't drift apart on how a case_remark cell is read.

    Args:
        cell: The raw cell value from `row.get("case_remark", "")`.

    Returns:
        A tuple of (case_remark_raw, parts, error). `parts` and `error` are
        both None when case_remark_raw is empty (nothing to parse).
    """
    # An empty CSV/Excel cell reads as NaN, not "", so check pd.isna first —
    # str(NaN) would otherwise become the literal string "nan".
    raw = "" if pd.isna(cell) else str(cell).strip()
    if not raw:
        return raw, None, None
    parts, error = parse_case_remark(raw)
    return raw, parts, error


def format_case_remark(parts: CaseRemarkParts) -> str:
    """Format parsed `case_remark` pieces into the OpenFloat Remark string.

    Examples:
        >>> format_case_remark(CaseRemarkParts("37166", "22505AA", "29400", "d05"))
        'Case #37166 | 22505AA | RESP | AIRTIME KSH 29400 | d05'
    """
    return (
        f"Case #{parts.case_number} | {parts.project_code} | RESP | "
        f"AIRTIME KSH {parts.amount} | {parts.activity_code}"
    )