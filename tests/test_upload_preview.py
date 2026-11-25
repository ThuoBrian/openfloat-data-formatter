"""Tests for upload_preview: what the column-mapping step shows, per file and picks."""

import pandas as pd

from openfloat_formatter.config import Settings
from openfloat_formatter.upload_preview import (
    PREVIEW_ROW_COUNT,
    describe_upload,
    identifier_summary,
    mapping_warnings,
    remark_preview,
)


def _settings(**update) -> Settings:
    return Settings().model_copy(update=update)


class TestDescribeUpload:
    def test_recognised_file_needs_no_picks(self, minimal_df):
        preview = describe_upload(minimal_df, _settings())

        assert preview.row_count == 2
        assert preview.missing_fields == []
        assert preview.mapping["airtime_phone"] == "airtime_phone"
        assert preview.mapping_warnings == []
        assert preview.identifier_column == "unique_id"
        assert preview.identifier_filled == 2

    def test_pick_fills_a_missing_field(self, minimal_df):
        raw = minimal_df.rename(columns={"amount": "Payout"})

        assert describe_upload(raw, _settings()).missing_fields == ["amount"]

        picked = describe_upload(raw, _settings(), {"amount": "Payout"})
        assert picked.missing_fields == []
        assert picked.detected.get("amount") is None
        assert picked.mapping["amount"] == "Payout"
        # The preview shows the frame as the pipeline reads it: canonical names.
        assert "amount" in picked.preview_columns

    def test_pick_naming_absent_column_still_warns(self, minimal_df):
        """A stale pick never reaches the mapping, but its warning must show."""
        preview = describe_upload(minimal_df, _settings(), {"amount": "Gone"})

        assert preview.mapping["amount"] == "amount"  # detection took over
        assert any("Gone" in warning for warning in preview.mapping_warnings)

    def test_identifier_choice_is_honoured(self, minimal_df):
        preview = describe_upload(minimal_df, _settings(account_name_column="survey"))

        assert preview.identifier_column == "survey"
        assert preview.identifier_samples == ["Baseline", "Baseline"]

    def test_empty_cells_preview_as_blank_not_nan(self, minimal_df):
        minimal_df.loc[0, "survey"] = None

        preview = describe_upload(minimal_df, _settings())

        survey = preview.preview_columns.index("survey")
        assert preview.preview_rows[0][survey] == ""

    def test_preview_is_capped(self, minimal_df):
        big = pd.concat([minimal_df] * 10, ignore_index=True)

        preview = describe_upload(big, _settings())

        assert preview.row_count == 20
        assert len(preview.preview_rows) == PREVIEW_ROW_COUNT

    def test_short_form_case_without_code(self, case_df):
        preview = describe_upload(case_df, _settings())

        assert preview.short_form_rows == 2
        assert preview.project_code_column is None
        assert preview.remark_preview == "C#38305"
        assert preview.remark_readable is True


class TestHelpers:
    def test_identifier_summary_skips_blanks(self):
        frame = pd.DataFrame({"Staff ID": ["A1", None, " ", "A2", "A3", "A4"]})

        filled, samples = identifier_summary(frame, "Staff ID")

        assert filled == 4
        assert samples == ["A1", "A2", "A3"]

    def test_corrected_pick_drops_its_warning(self, minimal_df):
        columns = minimal_df.columns
        detected = {"amount": "amount"}

        assert mapping_warnings(columns, {"amount": "amount"}, detected) == []

    def test_remark_preview_of_empty_frame(self, minimal_df):
        assert remark_preview(minimal_df.iloc[0:0], _settings()) == (None, False)

    def test_composed_remark_is_readable(self, case_df):
        remark, readable = remark_preview(case_df, _settings(project_code="22505AA"))

        assert remark == "C#38305 22505AA RESP AIRTIME-KSH350 g05"
        assert readable is True
