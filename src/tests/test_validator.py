"""Tests for the validator module — input validation and error collection."""

import pandas as pd
import pytest

from backend.config import Settings
from backend.models import IssueSeverity
from backend.validator import validate


class TestValidatorWithSampleData:
    """Test validation with the actual sample CSV data."""

    def test_sample_csv_all_valid(self, sample_df, default_config):
        """The sample CSV has 196 valid rows (all consent=Yes)."""
        report = validate(sample_df, default_config)
        assert report.total_rows == 196
        assert report.valid_rows == 196
        assert len(report.errors) == 0

    def test_sample_csv_no_consent_filters(self, sample_df, default_config):
        """No rows should be filtered for consent in the sample data."""
        report = validate(sample_df, default_config)
        assert report.filtered_counts.consent_filtered == 0


class TestValidatorConsentFilter:
    """Test consent filtering."""

    def test_consent_no_filters(self, minimal_df, default_config):
        """All-Yes consent rows are valid."""
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.consent_filtered == 0

    def test_consent_filters_no(self, minimal_df, default_config):
        """Rows with consent=No are filtered."""
        minimal_df.loc[0, "consent"] = "No"
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.consent_filtered == 1

    def test_consent_case_insensitive(self, minimal_df, default_config):
        """Consent matching is case-insensitive."""
        minimal_df.loc[0, "consent"] = "YES"
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.consent_filtered == 0

    def test_consent_empty(self, minimal_df, default_config):
        """Empty consent is filtered."""
        minimal_df.loc[0, "consent"] = ""
        report = validate(minimal_df, default_config)
        assert report.filtered_counts.consent_filtered == 1


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


class TestValidatorEmptyDataFrame:
    """Test edge cases with empty DataFrames."""

    def test_empty_df(self, default_config):
        """Empty DataFrame returns zero counts."""
        df = pd.DataFrame(columns=[
            "unique_id", "consent", "airtime_phone", "network",
            "submissiondate", "today", "amount",
            "project_name", "Project_Activity", "department", "survey",
        ])
        report = validate(df, default_config)
        assert report.total_rows == 0
        assert report.valid_rows == 0
        assert len(report.errors) == 0
        assert len(report.warnings) == 0