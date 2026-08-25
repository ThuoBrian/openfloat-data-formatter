"""Tests for the normalizer module — phone number and amount normalization."""

import pytest

from backend.normalizer import normalize_amount, normalize_phone


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