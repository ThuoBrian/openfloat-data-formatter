"""Tests for the normalizer module — phone number and amount normalization."""

import pytest

from backend.normalizer import (
    CaseRemarkParts,
    format_case_remark,
    normalize_amount,
    normalize_phone,
    parse_case_remark,
    resolve_case_remark,
)


class TestNormalizePhone:
    """Test phone number normalization per golden prompt §4.2."""

    def test_clean_nine_digit(self):
        """Standard 9-digit local number."""
        result, error = normalize_phone("785271309")
        assert result == "254785271309"
        assert error is None

    def test_with_254_prefix(self):
        """Number with country code prefix already included."""
        result, error = normalize_phone("254785271309")
        assert result == "254785271309"
        assert error is None

    def test_with_leading_zero(self):
        """Number with leading zero (local format)."""
        result, error = normalize_phone("0785271309")
        assert result == "254785271309"
        assert error is None

    def test_with_plus_and_spaces(self):
        """Number with + prefix and spaces."""
        result, error = normalize_phone("+254 785 271 309")
        assert result == "254785271309"
        assert error is None

    def test_with_dashes_and_parens(self):
        """Number with dashes and parentheses."""
        result, error = normalize_phone("(254) 785-271-309")
        assert result == "254785271309"
        assert error is None

    def test_integer_input(self):
        """Integer phone number input."""
        result, error = normalize_phone(785271309)
        assert result == "254785271309"
        assert error is None

    def test_float_input(self):
        """Float phone number input (from Excel)."""
        result, error = normalize_phone(785271309.0)
        assert result == "254785271309"
        assert error is None

    def test_too_short(self):
        """Number that is too short after stripping."""
        result, error = normalize_phone("123")
        assert result == ""
        assert "not 9 digits" in error

    def test_too_long(self):
        """Number that is too long after stripping prefixes."""
        result, error = normalize_phone("25478527130999")
        assert result == ""
        assert "not 9 digits" in error

    def test_non_numeric(self):
        """Non-numeric input."""
        result, error = normalize_phone("abcdefghi")
        assert result == ""

    def test_empty_string(self):
        """Empty string input."""
        result, error = normalize_phone("")
        assert result == ""
        assert error is not None

    def test_254_with_leading_zero_after_strip(self):
        """254 prefix removed, 9 digits remain (012345678): kept as-is since it's already 9 digits."""
        result, error = normalize_phone("254012345678")
        assert result == "254012345678"
        assert error is None

    def test_custom_country_prefix(self):
        """Custom country prefix (e.g., 255 for Tanzania)."""
        result, error = normalize_phone("712345678", country_prefix="255")
        assert result == "255712345678"
        assert error is None


class TestNormalizeAmount:
    """Test amount normalization per golden prompt §4.4."""

    def test_string_amount(self):
        """String amount coerced to float."""
        result, error = normalize_amount("150")
        assert result == 150.0
        assert error is None

    def test_integer_amount(self):
        """Integer amount."""
        result, error = normalize_amount(150)
        assert result == 150.0
        assert error is None

    def test_float_amount(self):
        """Float amount."""
        result, error = normalize_amount(150.5)
        assert result == 150.5
        assert error is None

    def test_zero_amount(self):
        """Zero amount should be rejected."""
        result, error = normalize_amount(0)
        assert result == 0.0
        assert "not positive" in error

    def test_negative_amount(self):
        """Negative amount should be rejected."""
        result, error = normalize_amount(-50)
        assert result == 0.0
        assert "not positive" in error

    def test_non_numeric_amount(self):
        """Non-numeric amount should be rejected."""
        result, error = normalize_amount("abc")
        assert result == 0.0
        assert "not numeric" in error

    def test_empty_string_amount(self):
        """Empty string amount should be rejected."""
        result, error = normalize_amount("")
        assert result == 0.0
        assert error is not None


class TestParseCaseRemark:
    """Test case_remark parsing: 'C#<case> <project> RESP AIRTIME-KSH<amount> <activity>'."""

    def test_well_formed(self):
        """Standard well-formed case_remark string."""
        parts, error = parse_case_remark("C#37166 22505AA RESP AIRTIME-KSH29400 d05")
        assert error is None
        assert parts == CaseRemarkParts(
            case_number="37166", project_code="22505AA", amount="29400", activity_code="d05"
        )

    def test_extra_surrounding_whitespace(self):
        """Leading/trailing whitespace is tolerated."""
        parts, error = parse_case_remark("  C#1 A RESP AIRTIME-KSH50 B  ")
        assert error is None
        assert parts.case_number == "1"

    def test_missing_resp_marker(self):
        """Missing the RESP marker fails to parse."""
        parts, error = parse_case_remark("C#37166 22505AA AIRTIME-KSH29400 d05")
        assert parts is None
        assert "does not match expected format" in error

    def test_missing_case_prefix(self):
        """Missing the C# prefix fails to parse."""
        parts, error = parse_case_remark("37166 22505AA RESP AIRTIME-KSH29400 d05")
        assert parts is None
        assert error is not None

    def test_non_airtime_type_fails(self):
        """A transaction type other than AIRTIME fails to parse (falls back to raw text)."""
        parts, error = parse_case_remark("C#37166 22505AA RESP DATA-KSH29400 d05")
        assert parts is None
        assert error is not None

    def test_garbage_input(self):
        """Arbitrary free text fails to parse."""
        parts, error = parse_case_remark("not a case remark at all")
        assert parts is None
        assert error is not None

    def test_empty_string(self):
        """Empty string fails to parse."""
        parts, error = parse_case_remark("")
        assert parts is None
        assert error is not None


class TestFormatCaseRemark:
    """Test formatting parsed case_remark pieces into the OpenFloat Remark string."""

    def test_format(self):
        parts = CaseRemarkParts(
            case_number="37166", project_code="22505AA", amount="29400", activity_code="d05"
        )
        assert format_case_remark(parts) == "Case #37166 | 22505AA | RESP | AIRTIME KSH 29400 | d05"


class TestResolveCaseRemark:
    """Test the shared NaN-guard + parse helper used by both validator and transformer."""

    def test_well_formed(self):
        raw, parts, error = resolve_case_remark("C#37166 22505AA RESP AIRTIME-KSH29400 d05")
        assert raw == "C#37166 22505AA RESP AIRTIME-KSH29400 d05"
        assert parts.case_number == "37166"
        assert error is None

    def test_malformed(self):
        raw, parts, error = resolve_case_remark("not a valid case remark")
        assert raw == "not a valid case remark"
        assert parts is None
        assert error is not None

    def test_nan_cell(self):
        """A pandas NaN cell (empty CSV/Excel cell) resolves to empty, not the string 'nan'."""
        raw, parts, error = resolve_case_remark(float("nan"))
        assert raw == ""
        assert parts is None
        assert error is None

    def test_missing_column_default(self):
        """The typical row.get('case_remark', '') default of '' resolves cleanly."""
        raw, parts, error = resolve_case_remark("")
        assert raw == ""
        assert parts is None
        assert error is None