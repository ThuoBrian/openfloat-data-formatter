"""Phone number and field normalization for the OpenFloat Data Formatter.

Handles the normalization pipeline defined in the golden prompt §4.2:
1. Strip whitespace and special characters (-, (, ), +)
2. Remove 254 or 0 prefix → keep remaining 9 digits
3. Prepend country code for output
4. Reject numbers not exactly 9 digits after stripping
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, NamedTuple

import pandas as pd

from .config import (
    ACCOUNT_NAME_COLUMNS,
    ACCOUNT_NAME_EXCLUDE_TOKENS,
    ACCOUNT_NAME_ID_TOKENS,
    ACCOUNT_NAME_KEYWORDS,
)


def normalize_phone(
    raw: str | int | float | None,
    country_prefix: str = "254",
) -> tuple[str, str | None]:
    """Normalize a phone number to international format.

    Args:
        raw: The raw phone number from Process Maker (string, int, float, or
            an empty cell read by pandas as None/NaN).
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
    # An empty cell arrives as NaN (pandas makes the whole column float64 as
    # soon as one phone is blank), and int(NaN) raises rather than returning a
    # hard error — that would abort the upload instead of flagging one row.
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ("", "Phone number is empty")

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
    r"^C#\s*(?P<case_number>\d+)\s+(?P<project_code>\S+)\s+RESP\s+"
    r"AIRTIME-KSH(?P<amount>\d+)\s+(?P<activity_code>\S+)$"
)

# Short form: the case number on its own, as typed in some exports.
# Example: "C# 38305" — no project code, amount or activity code to work with.
_SHORT_CASE_REMARK_PATTERN = re.compile(r"^C#\s*(?P<case_number>\d+)$")


class CaseRemarkParts(NamedTuple):
    """Structured pieces parsed out of a manually-typed `case_remark` string.

    Only `case_number` is always present. The rest are None when the remark was
    typed in the short `C#<case_number>` form, so every reader must handle that
    — in particular `amount`, which statement.py treats as the per-case total.
    """

    case_number: str
    project_code: str | None = None
    amount: str | None = None
    activity_code: str | None = None


def parse_case_remark(raw: str) -> tuple[CaseRemarkParts | None, str | None]:
    """Parse a manually-typed `case_remark` string into its component pieces.

    Two accepted formats, both with optional space after `C#`:

    - Full: `C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>`
    - Short: `C#<case_number>` — just the case number, as some exports type it.

    A partially-typed reference (the full form with pieces missing) is still an
    error: only these two shapes parse, so a truncated remark is caught rather
    than silently read as a short one.

    Args:
        raw: The raw case_remark value entered by the user.

    Returns:
        A tuple of (parts, error_message).
        On success: (CaseRemarkParts(...), None) — with project_code, amount
        and activity_code set to None for the short form.
        On failure: (None, error_description)

    Examples:
        >>> parts, error = parse_case_remark("C#37166 22505AA RESP AIRTIME-KSH29400 d05")
        >>> parts == CaseRemarkParts(
        ...     case_number='37166', project_code='22505AA', amount='29400', activity_code='d05')
        True
        >>> error is None
        True
        >>> parse_case_remark("C# 38305")[0]
        CaseRemarkParts(case_number='38305', project_code=None, amount=None, activity_code=None)
        >>> parse_case_remark("garbage")[0] is None
        True
    """
    cleaned = raw.strip()
    match = _CASE_REMARK_PATTERN.match(cleaned)
    if match is not None:
        return (
            CaseRemarkParts(
                case_number=match.group("case_number"),
                project_code=match.group("project_code"),
                amount=match.group("amount"),
                activity_code=match.group("activity_code"),
            ),
            None,
        )

    short_match = _SHORT_CASE_REMARK_PATTERN.match(cleaned)
    if short_match is not None:
        return CaseRemarkParts(case_number=short_match.group("case_number")), None

    return (
        None,
        f"case_remark '{raw}' does not match expected format "
        f"'C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>' "
        f"or 'C#<case_number>'",
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


def read_text_cell(cell: Any) -> str:
    """Read a text cell from an input row, guarding against pandas NaN.

    Centralizes the NaN-guard so every caller reads cells the same way —
    str(NaN) would otherwise write the literal string "nan" into the output.

    Args:
        cell: A raw cell value.

    Returns:
        The trimmed text, or "" when the cell is empty/absent.
    """
    return "" if pd.isna(cell) else str(cell).strip()


def _header_key(name: object) -> str:
    """Normalize a column header for tolerant matching.

    Lower-cases and drops spaces, underscores, hyphens, dots and slashes, so
    'Staff ID', 'staff_id' and 'staffid' all collapse to the same key. Also
    absorbs the stray trailing spaces real exports pick up ('Staff Name ').
    """
    return re.sub(r"[\s_\-./]+", "", str(name).strip().lower())


_CANONICAL_KEYS = frozenset(_header_key(name) for name in ACCOUNT_NAME_COLUMNS)


def _score_header(key: str) -> int:
    """Score how much a normalized header looks like an identifier column."""
    if any(token in key for token in ACCOUNT_NAME_EXCLUDE_TOKENS):
        return 0
    if key in _CANONICAL_KEYS:
        return 4
    has_keyword = any(token in key for token in ACCOUNT_NAME_KEYWORDS)
    has_id_token = any(
        key.startswith(token) or key.endswith(token) for token in ACCOUNT_NAME_ID_TOKENS
    )
    if has_keyword and has_id_token:
        return 3
    if has_keyword or key == "id":
        return 2
    if has_id_token:
        return 1
    return 0


def find_account_name_column(
    columns: Iterable[object],
    override: str | None = None,
    frame: pd.DataFrame | None = None,
) -> str | None:
    """Pick the input column whose values become the output 'Account Name'.

    Exports name that column per run — `unique_id`, `Staff ID`, `Staff`,
    `Respondent ID`, `respo`, `Beneficiary Ref` — so it is detected by shape
    instead of matched against a fixed list: a keyword (staff/resp/unique/case/
    reso/beneficiary/participant/enumerator) and/or an ID-ish token (id/number/
    ref/code), with 'Name', 'Phone', 'Amount', 'Remark' and friends rejected
    outright. Highest score wins, ties break leftmost.

    Resolve this ONCE per DataFrame and read every row from the column it
    returns — resolving per row lets one blank cell silently pull that row's
    Account Name from a different column than its neighbours.

    Args:
        columns: The input file's column headers.
        override: An explicit column chosen by the user (UI picker) or set via
            `ACCOUNT_NAME_COLUMN`. Matched exactly first, then by `_header_key`
            so 'staff id' finds 'Staff ID'. An override naming a column the file
            does not have falls back to detection rather than blanking the
            output — a stale .env must not break an otherwise fine run.
        frame: The DataFrame those columns came from. When given, a candidate
            that is entirely empty is passed over in favour of the next-best one
            that holds data.

    Returns:
        The chosen column, or None when nothing in the file looks like an
        identifier.
    """
    names = list(columns)
    if override:
        if override in names:
            return override
        matched = {_header_key(name): name for name in names}.get(_header_key(override))
        if matched is not None:
            return str(matched)

    scored = [(_score_header(_header_key(name)), -position, name)
              for position, name in enumerate(names)]
    ranked = [name for score, _, name in sorted(scored, reverse=True) if score > 0]
    if not ranked:
        return None

    # Prefer the best-scoring candidate that actually holds data. A file
    # carrying both an empty `unique_id` and a populated `Staff ID` should use
    # Staff ID for every row, rather than blanking the whole column.
    if frame is not None:
        for name in ranked:
            if any(read_text_cell(cell) for cell in frame[name]):
                return str(name)
    return str(ranked[0])


def format_case_remark(parts: CaseRemarkParts) -> str:
    """Format parsed `case_remark` pieces into the OpenFloat Remark string.

    Emits the same fixed case-reference format the input uses:
        C#<case_number> <project_code> RESP AIRTIME-KSH<amount> <activity_code>

    A remark typed in the short form comes back out short (`C#38305`) — there is
    nothing to pad it with, and inventing a project code or amount would put a
    fabricated figure in front of finance.

    Going out in this exact shape matters because OpenFloat echoes the Remark
    back in its Transaction Statement export, where `statement.py` parses it
    with `parse_case_remark` to roll payments up per case. Round-tripping a
    parse of this output is what keeps that working; the only change from the
    typed input is canonical single-space separation.

    Examples:
        >>> format_case_remark(CaseRemarkParts("37166", "22505AA", "29400", "d05"))
        'C#37166 22505AA RESP AIRTIME-KSH29400 d05'
        >>> format_case_remark(CaseRemarkParts("38305"))
        'C#38305'
    """
    if parts.project_code is None or parts.amount is None or parts.activity_code is None:
        return f"C#{parts.case_number}"
    return (
        f"C#{parts.case_number} {parts.project_code} RESP "
        f"AIRTIME-KSH{parts.amount} {parts.activity_code}"
    )
