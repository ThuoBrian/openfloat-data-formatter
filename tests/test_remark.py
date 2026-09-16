"""Tests for remark.py — composing the output Remark's case reference."""

import pytest

from openfloat_formatter.normalizer import CaseRemarkParts, parse_case_remark
from openfloat_formatter.remark import (
    build_remark,
    build_remark_context,
    case_totals,
    find_project_code_column,
)


def _rows(df):
    return [row for _index, row in df.iterrows()]


def _context(df, config, eligible=None):
    return build_remark_context(df, config, eligible if eligible is not None else _rows(df))


class TestFindProjectCodeColumn:
    """The project-code column is matched by name, never guessed at."""

    @pytest.mark.parametrize(
        "column", ["project_code", "Project Code", "PROJ_CODE", "award_code", "project_number"]
    )
    def test_accepted_spellings(self, column):
        assert find_project_code_column([column, "amount"]) == column

    @pytest.mark.parametrize("column", ["project_name", "Project_Activity", "project"])
    def test_neighbouring_columns_never_match(self, column):
        """project_name sits beside it in every export and is not a code."""
        assert find_project_code_column([column, "amount"]) is None

    def test_absent(self, minimal_df):
        assert find_project_code_column(minimal_df.columns) is None


class TestCaseTotals:
    """Per-case totals, over the rows the caller says will reach the output."""

    def test_sums_rows_of_one_case(self, case_df):
        assert case_totals(_rows(case_df)) == {"38305": 350.0}

    def test_spacing_variants_collapse(self, case_df):
        """'C# 38305' and 'C#38305' are the same case."""
        assert list(case_totals(_rows(case_df))) == ["38305"]

    def test_separate_cases(self, minimal_df):
        minimal_df["case_remark"] = ["C#1", "C#2"]
        assert case_totals(_rows(minimal_df)) == {"1": 150.0, "2": 200.0}

    def test_full_form_rows_count_too(self, minimal_df):
        minimal_df["case_remark"] = [
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
            "C# 38305",
        ]
        assert case_totals(_rows(minimal_df)) == {"38305": 350.0}

    def test_ignores_unparseable_and_empty(self, minimal_df):
        minimal_df["case_remark"] = ["garbage", ""]
        assert case_totals(_rows(minimal_df)) == {}

    def test_empty_input(self):
        assert case_totals([]) == {}


class TestComposeRemark:
    """Short references are completed; everything else is left alone."""

    def test_composes_with_case_total(self, case_df, default_config):
        """The amount is the per-case total (150 + 200), not the row's own."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        context = _context(case_df, config)
        results = [build_remark(row, context) for row in _rows(case_df)]
        assert [r.remark for r in results] == [
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
        ]
        assert [r.warning for r in results] == [None, None]

    def test_composed_reference_round_trips(self, case_df, default_config):
        """What goes out must parse back to the same pieces on the statement."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        remark = build_remark(case_df.iloc[0], _context(case_df, config)).remark
        assert parse_case_remark(remark)[0] == CaseRemarkParts("38305", "22505AA", "350", "g05")

    def test_column_beats_configured_code(self, case_df, default_config):
        case_df["project_code"] = ["22601BB", "22601BB"]
        config = default_config.model_copy(update={"project_code": "22505AA"})
        remark = build_remark(case_df.iloc[0], _context(case_df, config)).remark
        assert "22601BB" in remark

    def test_blank_column_cell_falls_back_to_configured_code(self, case_df, default_config):
        case_df["project_code"] = ["", "22601BB"]
        config = default_config.model_copy(update={"project_code": "22505AA"})
        remark = build_remark(case_df.iloc[0], _context(case_df, config)).remark
        assert "22505AA" in remark

    def test_no_project_code_keeps_short_remark(self, case_df, default_config):
        """No per-row warning: build_remark_context says it once, file-level."""
        context = _context(case_df, default_config)
        result = build_remark(case_df.iloc[0], context)
        assert result.remark == "C#38305"
        assert result.warning is None
        assert len(context.file_warnings) == 1
        assert "no project code available" in context.file_warnings[0]

    def test_configured_code_with_a_space_is_refused_once(self, case_df, default_config):
        """A bad configured code is one file-level problem, not one per row."""
        config = default_config.model_copy(update={"project_code": "AGRA Project"})
        context = _context(case_df, config)
        result = build_remark(case_df.iloc[0], context)
        assert result.remark == "C#38305"
        assert result.warning is None
        assert any("cannot be used in a case reference" in w for w in context.file_warnings)

    def test_column_code_with_a_space_warns_on_its_row(self, case_df, default_config):
        """A bad value in the file's own column is row-specific."""
        case_df["project_code"] = ["AGRA Project", "22505AA"]
        context = _context(case_df, default_config)
        first, second = (build_remark(row, context) for row in _rows(case_df))
        assert first.remark == "C#38305"
        assert first.field == "project_code"
        assert "cannot be read back" in (first.warning or "")
        assert second.remark == "C#38305 22505AA RESP AIRTIME-KSH350 g05"

    def test_activity_code_taken_before_the_pipe(self, case_df, default_config):
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df["Project_Activity"] = ["g06|Communications", "g06|Communications"]
        assert build_remark(case_df.iloc[0], _context(case_df, config)).remark.endswith(" g06")

    def test_activity_value_without_a_pipe_used_whole(self, case_df, default_config):
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df["Project_Activity"] = ["fieldwork", "fieldwork"]
        assert build_remark(case_df.iloc[0], _context(case_df, config)).remark.endswith(
            " fieldwork"
        )

    def test_missing_activity_keeps_short_remark(self, case_df, default_config):
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df["Project_Activity"] = ["", ""]
        result = build_remark(case_df.iloc[0], _context(case_df, config))
        assert result.remark == "C#38305"
        assert "activity code" in (result.warning or "")

    def test_fractional_case_total_keeps_short_remark(self, case_df, default_config):
        """A half-shilling total cannot go in a reference and is not rounded away."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        case_df["amount"] = [150.25, 200.0]
        context = _context(case_df, config)
        assert build_remark(case_df.iloc[0], context).remark == "C#38305"
        assert any("not a whole number" in w for w in context.file_warnings)

    def test_case_absent_from_totals_does_not_raise(self, case_df, default_config):
        """validate() sees rows that were excluded from the totals."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        context = _context(case_df, config, eligible=[])
        assert build_remark(case_df.iloc[0], context).remark == "C#38305"

    def test_full_form_is_never_recomposed(self, minimal_df, default_config):
        """A typed reference wins, wrong-looking amount and all."""
        config = default_config.model_copy(update={"project_code": "22505AA"})
        minimal_df["case_remark"] = ["C#37166 13054AF RESP AIRTIME-KSH99999 d05", ""]
        result = build_remark(minimal_df.iloc[0], _context(minimal_df, config))
        assert result.remark == "C#37166 13054AF RESP AIRTIME-KSH99999 d05"

    def test_unparseable_remark_kept_verbatim(self, minimal_df, default_config):
        minimal_df["case_remark"] = ["not a reference", ""]
        assert (
            build_remark(minimal_df.iloc[0], _context(minimal_df, default_config)).remark
            == "not a reference"
        )

    def test_legacy_fallback(self, minimal_df, default_config):
        """No case_remark at all: the pre-case_remark project/activity fallback."""
        remark = build_remark(minimal_df.iloc[0], _context(minimal_df, default_config)).remark
        assert remark == "Test Project - g05|Testing"

    def test_legacy_fallback_never_writes_nan(self, minimal_df, default_config):
        """A blank project_name is dropped, not rendered as the string 'nan'."""
        minimal_df["project_name"] = [float("nan"), float("nan")]
        remark = build_remark(minimal_df.iloc[0], _context(minimal_df, default_config)).remark
        assert remark == "g05|Testing"


class TestTypedAmountCrossCheck:
    """A full-form amount is the per-case total, so it is checked against that."""

    def test_amount_matching_case_total_is_quiet(self, minimal_df, default_config):
        """Two rows of one case, each carrying the case total: correct, no warning.

        Regression: this warned on every row when the check compared the embedded
        amount against the row's own amount.
        """
        minimal_df["case_remark"] = [
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
            "C#38305 22505AA RESP AIRTIME-KSH350 g05",
        ]
        context = _context(minimal_df, default_config)
        assert [build_remark(row, context).warning for row in _rows(minimal_df)] == [None, None]

    def test_amount_disagreeing_with_case_total_warns(self, minimal_df, default_config):
        minimal_df["case_remark"] = ["C#38305 22505AA RESP AIRTIME-KSH99 g05", ""]
        result = build_remark(minimal_df.iloc[0], _context(minimal_df, default_config))
        assert "does not match" in (result.warning or "")
        assert result.field == "case_remark"
