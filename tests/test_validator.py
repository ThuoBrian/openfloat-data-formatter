"""Tests for the validator module — input validation and error collection."""

import pandas as pd

from openfloat_formatter.validator import validate


class TestValidatorWithSampleData:
    """Test validation with the actual sample CSV data."""

    def test_sample_csv_all_valid(self, sample_df, default_config):
        """The sample CSV has 196 valid rows."""
        report = validate(sample_df, default_config)
        assert report.total_rows == 196
        assert report.valid_rows == 196
        assert len(report.errors) == 0


class TestValidatorConsentIgnored:
    """Consent is not part of the input schema, and never filters a row."""

    def test_legacy_consent_column_is_ignored(self, minimal_df, default_config):
        """An older export still carrying consent=No validates cleanly."""
        minimal_df["consent"] = ["No", ""]
        report = validate(minimal_df, default_config)
        assert report.valid_rows == 2
        assert len(report.errors) == 0


def _id_warnings(report):
    return [w for w in report.warnings if w.field == "account_name"]


class TestValidatorAccountName:
    """The identifier feeding the output Account Name — missing is a soft warning."""

    def test_present_unique_id_no_warning(self, minimal_df, default_config):
        """A populated unique_id raises no warning."""
        assert _id_warnings(validate(minimal_df, default_config)) == []

    def test_blank_unique_id_warns_but_keeps_row(self, minimal_df, default_config):
        """A blank identifier warns; the row is still valid."""
        minimal_df.loc[0, "unique_id"] = ""
        report = validate(minimal_df, default_config)
        assert len(_id_warnings(report)) == 1
        assert _id_warnings(report)[0].row_number == 2
        assert report.valid_rows == 2
        assert len(report.errors) == 0

    def test_missing_unique_id_cell_warns(self, minimal_df, default_config):
        """An empty CSV/Excel cell reads as NaN and warns the same way."""
        minimal_df.loc[0, "unique_id"] = float("nan")
        assert len(_id_warnings(validate(minimal_df, default_config))) == 1

    def test_staff_export_shape_is_accepted(self, minimal_df, default_config):
        """An export with 'Staff ID' next to 'Staff Name' warns about nothing."""
        staff_df = minimal_df.rename(columns={"unique_id": "Staff ID"})
        staff_df["Staff Name "] = ["Test Person", "Other Person"]
        assert _id_warnings(validate(staff_df, default_config)) == []

    def test_no_id_column_at_all_warns_every_row(self, minimal_df, default_config):
        """With no ID-shaped column, every row warns — the tell for a bad header."""
        no_id_df = minimal_df.rename(columns={"unique_id": "label"})
        id_warnings = _id_warnings(validate(no_id_df, default_config))
        assert len(id_warnings) == 2
        assert "no identifier column found" in id_warnings[0].message

    def test_blank_cell_message_names_the_column(self, minimal_df, default_config):
        """A blank cell and a missing column are different problems, said differently."""
        minimal_df.loc[0, "unique_id"] = ""
        message = _id_warnings(validate(minimal_df, default_config))[0].message
        assert "'unique_id' is empty" in message

    def test_explicit_column_is_used(self, minimal_df, default_config):
        """An override picks a column detection would never have chosen."""
        config = default_config.model_copy(update={"account_name_column": "survey"})
        assert _id_warnings(validate(minimal_df, config)) == []

    def test_stale_override_warns_once_and_falls_back(self, minimal_df, default_config):
        """A configured column missing from the file: one file-level warning, no per-row noise."""
        config = default_config.model_copy(update={"account_name_column": "Staff ID"})
        id_warnings = _id_warnings(validate(minimal_df, config))
        assert len(id_warnings) == 1
        assert id_warnings[0].row_number == 1
        assert "falling back to 'unique_id'" in id_warnings[0].message


class TestValidatorPhoneValidation:
    """Test phone number validation in the validator context."""

    def test_invalid_phone(self, minimal_df, default_config):
        """Invalid phone numbers produce errors."""
        minimal_df.loc[0, "airtime_phone"] = "123"  # Too short
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.invalid_phone == 1
        # Find the phone error
        phone_errors = [e for e in report.errors if e.field == "airtime_phone"]
        assert len(phone_errors) >= 1


class TestValidatorAmountValidation:
    """Test amount validation."""

    def test_invalid_amount_string(self, minimal_df, default_config):
        """Non-numeric amount produces an error."""
        minimal_df["amount"] = minimal_df["amount"].astype(object)
        minimal_df.loc[0, "amount"] = "abc"
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.invalid_amount == 1

    def test_negative_amount(self, minimal_df, default_config):
        """Negative amount produces an error."""
        minimal_df.loc[0, "amount"] = -50
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.invalid_amount == 1

    def test_high_amount_warning(self, minimal_df, default_config):
        """Amount above threshold produces a warning (not error)."""
        minimal_df.loc[0, "amount"] = 50000
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.invalid_amount == 0  # Not an error
        high_amount_warnings = [
            w for w in report.warnings if w.field == "amount"
        ]
        assert len(high_amount_warnings) >= 1


class TestValidatorNetworkMapping:
    """Test network mapping validation."""

    def test_unmapped_network(self, minimal_df, default_config):
        """Unrecognized network produces an error."""
        minimal_df.loc[0, "network"] = "Orange"
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.unmapped_network == 1
        network_errors = [e for e in report.errors if e.field == "network"]
        assert len(network_errors) >= 1


class TestValidatorDuplicates:
    """Test duplicate phone detection."""

    def test_duplicate_phone_warning(self, minimal_df, default_config):
        """Duplicate phone numbers produce a warning."""
        minimal_df.loc[1, "airtime_phone"] = "712345678"  # Same as row 0
        report = validate(minimal_df, default_config)
        dup_warnings = [w for w in report.warnings if w.field == "airtime_phone"]
        assert len(dup_warnings) >= 1

    def test_no_duplicates(self, minimal_df, default_config):
        """No duplicate warnings for unique phones."""
        report = validate(minimal_df, default_config)
        dup_warnings = [w for w in report.warnings if "Duplicate" in w.message]
        assert len(dup_warnings) == 0


class TestValidatorCaseRemark:
    """Test case_remark format checking (soft warning, row still included)."""

    def test_short_case_remark_no_warning(self, minimal_df, default_config):
        """'C# 38305' is a valid reference — no parse warning, no amount cross-check."""
        minimal_df["case_remark"] = ["C# 38305", "C#38306"]
        report = validate(minimal_df, default_config)
        assert [w for w in report.warnings if w.field == "case_remark"] == []

    def test_well_formed_case_remark_no_warning(self, minimal_df, default_config):
        """A well-formed case_remark whose amount matches the Amount column produces no warning."""
        # minimal_df's amount column is [150, 200] — the embedded amounts must match.
        minimal_df["case_remark"] = [
            "C#37166 22505AA RESP AIRTIME-KSH150 d05",
            "C#37167 22505AA RESP AIRTIME-KSH200 d05",
        ]
        report = validate(minimal_df, default_config)
        case_remark_warnings = [w for w in report.warnings if w.field == "case_remark"]
        assert len(case_remark_warnings) == 0

    def test_amount_mismatch_warns(self, minimal_df, default_config):
        """A case_remark amount that disagrees with the Amount column produces a warning."""
        # Row 0's real amount is 150, but the case_remark claims 29400.
        minimal_df["case_remark"] = [
            "C#37166 22505AA RESP AIRTIME-KSH29400 d05",
            "",
        ]
        report = validate(minimal_df, default_config)
        case_remark_warnings = [w for w in report.warnings if w.field == "case_remark"]
        assert len(case_remark_warnings) == 1
        assert "does not match" in case_remark_warnings[0].message
        # Soft warning only — row is still valid.
        assert report.valid_rows == 2

    def test_malformed_case_remark_warns(self, minimal_df, default_config):
        """A malformed case_remark produces a warning but does not exclude the row."""
        minimal_df["case_remark"] = ["not a valid case remark", ""]
        report = validate(minimal_df, default_config)
        case_remark_warnings = [w for w in report.warnings if w.field == "case_remark"]
        assert len(case_remark_warnings) == 1
        assert case_remark_warnings[0].row_number == 2  # 1-based + header row
        # Row is still valid (soft warning, not a hard error)
        assert report.valid_rows == 2

    def test_missing_case_remark_no_warning(self, minimal_df, default_config):
        """No case_remark column at all produces no warning (legacy behavior)."""
        report = validate(minimal_df, default_config)
        case_remark_warnings = [w for w in report.warnings if w.field == "case_remark"]
        assert len(case_remark_warnings) == 0

    def test_nan_case_remark_no_warning(self, minimal_df, default_config):
        """An empty CSV/Excel cell (read as NaN by pandas) produces no warning.

        Regression test: str(float('nan')) == 'nan', which must not be treated
        as a malformed case_remark value.
        """
        minimal_df["case_remark"] = [float("nan"), float("nan")]
        report = validate(minimal_df, default_config)
        case_remark_warnings = [w for w in report.warnings if w.field == "case_remark"]
        assert len(case_remark_warnings) == 0


class TestValidatorEmptyDataFrame:
    """Test edge cases with empty DataFrames."""

    def test_empty_df(self, default_config):
        """Empty DataFrame returns zero counts."""
        df = pd.DataFrame(columns=[
            "unique_id", "airtime_phone", "network",
            "submissiondate", "today", "amount",
            "project_name", "Project_Activity", "department", "survey",
        ])
        report = validate(df, default_config)
        assert report.total_rows == 0
        assert report.valid_rows == 0
        assert len(report.errors) == 0
        assert len(report.warnings) == 0
