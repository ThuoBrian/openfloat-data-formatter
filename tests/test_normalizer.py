"""Tests for the normalizer module — phone number and amount normalization."""


import pandas as pd
import pytest

from openfloat_formatter.normalizer import (
    CaseRemarkParts,
    find_account_name_column,
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
        assert "not 9 digits" in (error or "")

    def test_too_long(self):
        """Number that is too long after stripping prefixes."""
        result, error = normalize_phone("25478527130999")
        assert result == ""
        assert "not 9 digits" in (error or "")

    def test_non_numeric(self):
        """Non-numeric input."""
        result, _ = normalize_phone("abcdefghi")
        assert result == ""

    def test_empty_string(self):
        """Empty string input."""
        result, error = normalize_phone("")
        assert result == ""
        assert error is not None

    def test_254_with_leading_zero_after_strip(self):
        """254 stripped, leaving 9 digits (012345678) — kept as-is, already 9 digits."""
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
        assert "not positive" in (error or "")

    def test_negative_amount(self):
        """Negative amount should be rejected."""
        result, error = normalize_amount(-50)
        assert result == 0.0
        assert "not positive" in (error or "")

    def test_non_numeric_amount(self):
        """Non-numeric amount should be rejected."""
        result, error = normalize_amount("abc")
        assert result == 0.0
        assert "not numeric" in (error or "")

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

    def test_short_form(self):
        """Some exports type just the case number: 'C# 38305'."""
        parts, error = parse_case_remark("C# 38305")
        assert error is None
        assert parts == CaseRemarkParts(case_number="38305")
        assert parts.amount is None

    @pytest.mark.parametrize("raw", ["C#38305", "C# 38305", "  C#  38305  "])
    def test_short_form_spacing(self, raw):
        """The space after 'C#' is optional in both forms."""
        parts, error = parse_case_remark(raw)
        assert error is None
        assert parts is not None
        assert parts.case_number == "38305"

    def test_full_form_tolerates_space_after_hash(self):
        parts, error = parse_case_remark("C# 37166 22505AA RESP AIRTIME-KSH29400 d05")
        assert error is None
        assert parts is not None
        assert parts.project_code == "22505AA"

    @pytest.mark.parametrize(
        "raw",
        [
            "C#37166 22505AA RESP",
            "C#37166 22505AA RESP AIRTIME-KSH29400",
            "C#",
            "C# abc",
            "38305",
        ],
    )
    def test_partial_reference_is_still_an_error(self, raw):
        """A half-typed full form must not be read as a short one."""
        parts, error = parse_case_remark(raw)
        assert parts is None
        assert error is not None

    def test_extra_surrounding_whitespace(self):
        """Leading/trailing whitespace is tolerated."""
        parts, error = parse_case_remark("  C#1 A RESP AIRTIME-KSH50 B  ")
        assert error is None
        assert parts is not None
        assert parts.case_number == "1"

    def test_missing_resp_marker(self):
        """Missing the RESP marker fails to parse."""
        parts, error = parse_case_remark("C#37166 22505AA AIRTIME-KSH29400 d05")
        assert parts is None
        assert "does not match expected format" in (error or "")

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
        assert format_case_remark(parts) == "C#37166 22505AA RESP AIRTIME-KSH29400 d05"

    def test_short_form_stays_short(self):
        """Nothing to pad a short remark with — never invent a project code or amount."""
        assert format_case_remark(CaseRemarkParts("38305")) == "C#38305"

    def test_short_form_round_trips(self):
        """The short Remark written to the upload must parse back out of the statement."""
        parts, error = parse_case_remark(format_case_remark(CaseRemarkParts("38305")))
        assert error is None
        assert parts == CaseRemarkParts(case_number="38305")

    def test_round_trips_through_parse(self):
        """The Remark written to the upload must parse back out of the statement.

        OpenFloat echoes Remark into its Transaction Statement, where
        statement.py re-parses it with parse_case_remark to roll up per case.
        """
        parts = CaseRemarkParts(
            case_number="37166", project_code="22505AA", amount="29400", activity_code="d05"
        )
        reparsed, error = parse_case_remark(format_case_remark(parts))
        assert error is None
        assert reparsed == parts

    def test_canonicalizes_spacing(self):
        """Ragged input spacing comes out single-spaced but otherwise identical."""
        parts, _ = parse_case_remark("C#37166   22505AA  RESP   AIRTIME-KSH29400  d05")
        assert parts is not None
        assert format_case_remark(parts) == "C#37166 22505AA RESP AIRTIME-KSH29400 d05"


# The header row of a real staff airtime export. Hardcoded on purpose: the file
# it came from holds staff names and phone numbers, so no test may read it.
STAFF_EXPORT_HEADERS = [
    "Staff ID",
    "Staff Name ",
    "airtime_phone",
    "network",
    "amount",
    "project_name",
    "Project_Activity",
    "department",
    "survey",
    "case_remark",
]


class TestFindAccountNameColumn:
    """Detecting the identifier column whatever the export called it."""

    def test_staff_export_picks_staff_id(self):
        """Regression: 'Staff ID' must win over 'Staff Name ' in a real export."""
        assert find_account_name_column(STAFF_EXPORT_HEADERS) == "Staff ID"

    def test_case_remark_is_never_the_identifier(self):
        """'case_remark' contains the keyword 'case' — the exclude list must reject it."""
        assert find_account_name_column(["airtime_phone", "case_remark", "amount"]) is None

    @pytest.mark.parametrize(
        "column",
        [
            "unique_id",
            "Unique id",
            "Staff ID",
            "staff_id",
            "STAFFID",
            "Staff",
            "Respondent ID",
            "respo",
            "Resp ID",
            "Case ID",
            "Reso ID",
            "Beneficiary Ref",
            "Staff Number",
            "participant code",
            "ID",
        ],
    )
    def test_accepted_spellings(self, column):
        """Detection is by shape, so unlisted-but-ID-shaped headers still resolve."""
        assert find_account_name_column([column, "airtime_phone", "amount"]) == column

    def test_id_suffix_beats_bare_keyword(self):
        """'Staff ID' outranks 'Staff' even though it is further right."""
        assert find_account_name_column(["Staff", "Staff ID"]) == "Staff ID"

    def test_canonical_name_outranks_other_id_shapes(self):
        """A canonical alias beats an ID-shaped header that isn't one."""
        assert find_account_name_column(["Beneficiary Ref", "unique_id"]) == "unique_id"

    def test_ties_break_leftmost(self):
        """Two equally canonical columns: the first one in the file wins."""
        assert find_account_name_column(["Case ID", "Staff ID"]) == "Case ID"

    def test_name_columns_are_rejected(self):
        """A '<keyword> Name' column must never be chosen."""
        assert find_account_name_column(["Respondent Name", "Respondent ID"]) == "Respondent ID"

    def test_no_candidate_returns_none(self):
        assert find_account_name_column(["label", "airtime_phone", "network", "amount"]) is None

    def test_prefers_a_column_that_holds_data(self):
        """An entirely empty unique_id must not shadow a populated Staff ID."""
        frame = pd.DataFrame({"unique_id": ["", ""], "Staff ID": ["93128", "93129"]})
        assert find_account_name_column(frame.columns, frame=frame) == "Staff ID"

    def test_keeps_best_column_when_nothing_holds_data(self):
        """With no data anywhere, still name the best candidate so messages can cite it."""
        frame = pd.DataFrame({"unique_id": ["", ""], "amount": [1, 2]})
        assert find_account_name_column(frame.columns, frame=frame) == "unique_id"

    def test_override_wins(self):
        assert find_account_name_column(["unique_id", "survey"], override="survey") == "survey"

    def test_override_matched_tolerantly(self):
        """'staff_id' in a .env finds a header written 'Staff ID '."""
        assert find_account_name_column(["Staff ID ", "amount"], override="staff_id") == "Staff ID "

    def test_stale_override_falls_back_to_detection(self):
        """A column that isn't in the file must not blank the output."""
        assert find_account_name_column(["unique_id"], override="Staff ID") == "unique_id"


class TestResolveCaseRemark:
    """Test the shared NaN-guard + parse helper used by both validator and transformer."""

    def test_well_formed(self):
        raw, parts, error = resolve_case_remark("C#37166 22505AA RESP AIRTIME-KSH29400 d05")
        assert raw == "C#37166 22505AA RESP AIRTIME-KSH29400 d05"
        assert parts is not None
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
