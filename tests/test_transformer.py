"""Tests for the transformer module — end-to-end transformation pipeline."""


from openfloat_formatter.normalizer import parse_case_remark
from openfloat_formatter.transformer import _build_output_rows, transform


class TestTransformWithSampleData:
    """End-to-end transformation with the real sample CSV."""

    def test_transform_sample_csv(self, sample_csv_path, default_config):
        """Transform the sample CSV and verify output."""
        result = transform(sample_csv_path, default_config)
        assert result.output is not None
        assert result.output_row_count > 0

    def test_transform_output_row_count(self, sample_csv_path, default_config):
        """All 196 rows in the sample CSV should transform successfully."""
        result = transform(sample_csv_path, default_config)
        # All rows have valid phones, valid amounts, known networks
        assert result.output_row_count == 196
        assert result.validation_report.total_rows == 196

    def test_transform_no_errors(self, sample_csv_path, default_config):
        """No hard errors in the sample data."""
        result = transform(sample_csv_path, default_config)
        assert len(result.validation_report.errors) == 0


class TestTransformOutputFormat:
    """Verify the output Excel file format."""

    def test_output_is_bytes_io(self, sample_csv_path, default_config):
        """Output is a BytesIO object when no output_path is specified."""
        from io import BytesIO

        result = transform(sample_csv_path, default_config)
        assert isinstance(result.output, BytesIO)

    def test_output_readable_as_excel(self, sample_csv_path, default_config):
        """Output can be read as a valid Excel file."""
        import openpyxl

        result = transform(sample_csv_path, default_config)
        assert result.output is not None
        result.output.seek(0)
        wb = openpyxl.load_workbook(result.output)
        assert "Accounts" in wb.sheetnames
        assert "Allowed Types" in wb.sheetnames
        wb.close()


class TestBuildOutputRows:
    """Test the _build_output_rows helper."""

    def test_basic_transformation(self, minimal_df, default_config):
        """Minimal valid DataFrame produces correct output rows."""
        rows, errors = _build_output_rows(minimal_df, default_config)
        assert len(rows) == 2
        assert len(errors) == 0

    def test_phone_normalization(self, minimal_df, default_config):
        """Phone numbers are normalized with 254 prefix."""
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].account_number == "254712345678"
        assert rows[0].notification_phone_number == "254712345678"

    def test_network_mapping(self, minimal_df, default_config):
        """Networks are mapped to correct account types."""
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].account_type == "Safaricom Prepaid"
        assert rows[1].account_type == "Airtel Prepaid"

    def test_account_name_from_unique_id(self, minimal_df, default_config):
        """Account Name is the unique_id (Respondent/Staff/Case/Reso ID) verbatim."""
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].account_name == "TEST001"
        assert rows[1].account_name == "TEST002"

    def test_account_name_from_staff_id_column(self, minimal_df, default_config):
        """An export that calls the ID column 'Staff ID' still fills Account Name."""
        staff_df = minimal_df.rename(columns={"unique_id": "Staff ID"})
        staff_df["Staff Name "] = ["Test Person", "Other Person"]
        rows, _ = _build_output_rows(staff_df, default_config)
        assert rows[0].account_name == "TEST001"

    def test_case_remark_is_never_the_account_name(self, minimal_df, default_config):
        """With no ID column, Account Name is blank — case_remark must not stand in."""
        no_id_df = minimal_df.rename(columns={"unique_id": "label"})
        no_id_df["case_remark"] = ["C#37166 22505AA RESP AIRTIME-KSH150 d05", ""]
        rows, _ = _build_output_rows(no_id_df, default_config)
        assert [row.account_name for row in rows] == ["", ""]

    def test_explicit_column_overrides_detection(self, minimal_df, default_config):
        """The UI picker's choice wins over what detection would have picked."""
        config = default_config.model_copy(update={"account_name_column": "survey"})
        rows, _ = _build_output_rows(minimal_df, config)
        assert rows[0].account_name == "Baseline"

    def test_stale_override_falls_back_to_detection(self, minimal_df, default_config):
        """A stale ACCOUNT_NAME_COLUMN must not blank the upload."""
        config = default_config.model_copy(update={"account_name_column": "Staff ID"})
        rows, _ = _build_output_rows(minimal_df, config)
        assert rows[0].account_name == "TEST001"

    def test_blank_unique_id_gives_empty_account_name(self, minimal_df, default_config):
        """A NaN unique_id writes an empty Account Name, never the string "nan"."""
        minimal_df.loc[0, "unique_id"] = float("nan")
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].account_name == ""

    def test_legacy_consent_column_ignored(self, minimal_df, default_config):
        """A leftover consent column excludes nothing — consent=No rows still output."""
        minimal_df["consent"] = ["No", ""]
        rows, errors = _build_output_rows(minimal_df, default_config)
        assert len(rows) == 2
        assert not errors

    def test_remark_format(self, minimal_df, default_config):
        """Remark falls back to 'project_name - Project_Activity' when case_remark is absent."""
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].remark == "Test Project - g05|Testing"

    def test_short_remark_composed_with_case_total(self, case_df, default_config):
        """Both rows carry the case total (350), not their own 150/200."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        rows, _ = _build_output_rows(case_df, config)
        assert [row.remark for row in rows] == [
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
        ]
        assert parse_case_remark(rows[0].remark)[1] is None

    def test_excluded_row_does_not_inflate_the_case_total(self, case_df, default_config):
        """A row dropped for a bad phone is not money OpenFloat is asked to send."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df.loc[0, "airtime_phone"] = "123"  # hard error: excluded from output
        rows, _ = _build_output_rows(case_df, config)
        assert len(rows) == 1
        assert rows[0].remark == "C#38305 22505AA RESP AIRTIME-KSH200 g05"

    def test_project_code_column_wins(self, case_df, default_config):
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df["project_code"] = ["22601BB", "22601BB"]
        rows, _ = _build_output_rows(case_df, config)
        assert rows[0].remark == "C#38305 22601BB RESP AIRTIME-KSH350 g05"

    def test_remark_from_short_case_remark(self, minimal_df, default_config):
        """A short 'C# 38305' is canonicalized to 'C#38305', not dumped as raw text."""
        minimal_df["case_remark"] = ["C# 38305", ""]
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].remark == "C#38305"
        assert parse_case_remark(rows[0].remark)[1] is None

    def test_remark_from_case_remark(self, minimal_df, default_config):
        """Remark is built from a well-formed case_remark, taking priority over project/activity."""
        minimal_df["case_remark"] = [
            "C#37166 22505AA RESP AIRTIME-KSH29400 d05",
            "",
        ]
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].remark == "C#37166 22505AA RESP AIRTIME-KSH29400 d05"
        # The statement reader must be able to parse the Remark back out.
        assert parse_case_remark(rows[0].remark)[1] is None
        # Row 1 has no case_remark, so it falls back to project/activity.
        assert rows[1].remark == "Test Project - g05|Testing"

    def test_remark_from_malformed_case_remark_falls_back_to_raw(self, minimal_df, default_config):
        """A case_remark not matching the pattern is kept verbatim (soft fallback)."""
        minimal_df["case_remark"] = ["not a valid case remark", ""]
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].remark == "not a valid case remark"

    def test_remark_nan_falls_back_to_project_activity(self, minimal_df, default_config):
        """An empty cell (NaN) falls back to project/activity, not the string 'nan'."""
        minimal_df["case_remark"] = [float("nan"), float("nan")]
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].remark == "Test Project - g05|Testing"

    def test_amount_coercion(self, minimal_df, default_config):
        """Amounts are coerced to float."""
        minimal_df["amount"] = minimal_df["amount"].astype(object)
        minimal_df.loc[0, "amount"] = "300"
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].amount == 300.0

    def test_invalid_phone_excluded(self, minimal_df, default_config):
        """Rows with invalid phone numbers are excluded."""
        minimal_df.loc[0, "airtime_phone"] = "123"  # Too short
        rows, errors = _build_output_rows(minimal_df, default_config)
        assert len(rows) == 1
        assert 0 in errors

    def test_unmapped_network_excluded(self, minimal_df, default_config):
        """Rows with unmapped networks are excluded."""
        minimal_df.loc[0, "network"] = "Orange"
        rows, errors = _build_output_rows(minimal_df, default_config)
        assert len(rows) == 1
        assert 0 in errors

    def test_invalid_amount_excluded(self, minimal_df, default_config):
        """Rows with invalid amounts are excluded."""
        minimal_df["amount"] = minimal_df["amount"].astype(object)
        minimal_df.loc[0, "amount"] = "abc"
        rows, errors = _build_output_rows(minimal_df, default_config)
        assert len(rows) == 1
        assert 0 in errors

    def test_optional_fields_blank(self, minimal_df, default_config):
        """Till/Paybill fields are blank in output."""
        rows, _ = _build_output_rows(minimal_df, default_config)
        assert rows[0].till_or_paybill_number == ""
        assert rows[0].till_or_paybill_business_name == ""
