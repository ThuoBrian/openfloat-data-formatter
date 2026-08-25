"""Phone number and field normalization for the OpenFloat Data Formatter.

Handles the normalization pipeline defined in the golden prompt §4.2:
1. Strip whitespace and special characters (-, (, ), +)
2. Remove 254 or 0 prefix → keep remaining 9 digits
3. Prepend country code for output
4. Reject numbers not exactly 9 digits after stripping
"""

from __future__ import annotations

import re


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