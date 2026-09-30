"""Tests for the Statement Report workbook — writer.write_statement_workbook.

Every report here is built from a synthetic statement (`make_statement_workbook`).
The real exports in sample_report_output/ hold staff names and phone numbers and
are never read by a test.
"""

import openpyxl
import pytest

from helpers import GOOD_DATE, GOOD_REMARK, statement_row
from openfloat_formatter.models import StatementReport, StatementTransaction
from openfloat_formatter.normalizer import parse_case_remark
from openfloat_formatter.statement import build_statement_report
from openfloat_formatter.writer import (
    remark_file_stem,
    write_finance_workbook,
    write_statement_workbook,
)

STATEMENT_HEADERS = [
    "Approval Id",
    "Transaction Id",
    "Transaction Type",
    "Transaction Status",
    "Date",
    "Account Name",
    "Account Number",
    "Account Type",
    "Remark",
    "Initiated By",
    "Approved/Rejected By",
    "Amount",
    "Reference Id",
]
# 0-based, for rows read back with values_only
S_STATUS = STATEMENT_HEADERS.index("Transaction Status")
S_AMOUNT = STATEMENT_HEADERS.index("Amount")
S_REFERENCE = STATEMENT_HEADERS.index("Reference Id")


def _load(write, report):
    """Write a report with `write` and open the result."""
    buffer = write(report)
    buffer.seek(0)
    return openpyxl.load_workbook(buffer)


def _rows(worksheet):
    return list(worksheet.iter_rows(min_row=2, values_only=True))


@pytest.fixture
def report(make_statement_workbook):
    """Two paid rows (100 + 250) and one Reversed row."""
    buffer = make_statement_workbook(
        rows=[
            statement_row(),
            statement_row(phone=254798765432, amount=250),
            statement_row(
                status="Reversed",
                phone=254722334455,
                amount=None,
                **{"Reference Id": "REF9"},
            ),
        ]
    )
    return build_statement_report([buffer], source_names=["august.xlsx"])


class TestSheets:
    """Which sheets the workbook has, and what lands on each."""

    def test_two_sheets_without_reconciliation(self, report):
        workbook = _load(write_statement_workbook, report)
        assert workbook.sheetnames == ["Successful", "Unsuccessful"]
        workbook.close()

    def test_reconciliation_sheets_when_an_input_was_supplied(
        self, make_statement_workbook, pm_input_df
    ):
        buffer = make_statement_workbook(rows=[statement_row()])
        reconciled = build_statement_report([buffer], input_df=pm_input_df)
        workbook = _load(write_statement_workbook, reconciled)
        assert workbook.sheetnames == [
            "Successful",
            "Unsuccessful",
            "Paid",
            "Matched but Unpaid",
            "Missing from Statement",
            "Not in Input",
        ]
        workbook.close()

    def test_headers(self, report):
        workbook = _load(write_statement_workbook, report)
        for title in ("Successful", "Unsuccessful"):
            assert [cell.value for cell in workbook[title][1]] == STATEMENT_HEADERS
        workbook.close()

    def test_successful_rows_only_on_the_first_sheet(self, report):
        workbook = _load(write_statement_workbook, report)
        statuses = [row[S_STATUS] for row in _rows(workbook["Successful"])][:-1]  # drop TOTAL
        assert statuses == ["Successful", "Successful"]
        workbook.close()

    def test_reversed_row_lands_unsuccessful_with_no_amount(self, report):
        workbook = _load(write_statement_workbook, report)
        data = _rows(workbook["Unsuccessful"])[:-1]  # drop TOTAL
        assert len(data) == 1
        row = data[0]
        assert row[S_STATUS] == "Reversed"
        assert row[S_REFERENCE] == "REF9"  # Reference Id survives
        assert row[S_AMOUNT] is None  # Amount blank, not zero
        workbook.close()

    def test_statement_fields_carried_across(self, report):
        workbook = _load(write_statement_workbook, report)
        row = _rows(workbook["Successful"])[0]
        assert row[:S_AMOUNT] == (
            "14886185",
            "18488654",
            "Payment",
            "Successful",
            GOOD_DATE,
            "9019830",
            254712345678,
            "Partner",
            GOOD_REMARK,
            "Test User",
            "Test Approver",
        )
        assert row[S_AMOUNT] == 100
        workbook.close()


class TestTotals:
    """The bold TOTAL row under each sheet."""

    def test_total_sums_the_amount_column(self, report):
        workbook = _load(write_statement_workbook, report)
        worksheet = workbook["Successful"]
        last = _rows(worksheet)[-1]
        assert last[0] == "TOTAL"
        assert last[S_AMOUNT] == 350.0  # 100 + 250
        workbook.close()

    def test_total_row_is_bold_and_formatted(self, report):
        workbook = _load(write_statement_workbook, report)
        worksheet = workbook["Successful"]
        label = worksheet.cell(row=worksheet.max_row, column=1)
        amount = worksheet.cell(row=worksheet.max_row, column=S_AMOUNT + 1)
        assert label.font.bold
        assert amount.font.bold
        assert amount.number_format == "#,##0"
        workbook.close()

    def test_reversed_rows_total_to_zero(self, report):
        """The Reversed row carries no amount, so its sheet totals nothing."""
        workbook = _load(write_statement_workbook, report)
        assert _rows(workbook["Unsuccessful"])[-1][S_AMOUNT] == 0.0
        workbook.close()

    def test_empty_sheet_has_no_total_row(self, make_statement_workbook):
        """Headers only — a bold zero would read like a finding."""
        buffer = make_statement_workbook(rows=[statement_row()])
        workbook = _load(write_statement_workbook, build_statement_report([buffer]))
        worksheet = workbook["Unsuccessful"]
        assert worksheet.max_row == 1
        assert _rows(worksheet) == []
        workbook.close()


class TestCellTypes:
    """Phones as numbers, and free text that cannot become a formula."""

    def test_account_number_written_as_a_number(self, report):
        workbook = _load(write_statement_workbook, report)
        column = STATEMENT_HEADERS.index("Account Number") + 1
        cell = workbook["Successful"].cell(row=2, column=column)
        assert cell.value == 254712345678
        assert isinstance(cell.value, int)
        assert cell.number_format == "0"
        workbook.close()

    def test_free_text_cannot_become_a_formula(self):
        """A Remark that looks like a formula is written as text, not executed.

        Built as a model rather than through a statement file on purpose: reading
        a .xlsx already neutralizes formulas, so this pins the writer's own guard.
        """
        report = StatementReport(
            transactions=[
                StatementTransaction(
                    file_name="august.xlsx",
                    row_number=2,
                    status="Successful",
                    is_successful=True,
                    account_name="TEST001",
                    account_number="254712345678",
                    remark='=HYPERLINK("http://evil","click")',
                    amount=100.0,
                )
            ]
        )
        workbook = _load(write_statement_workbook, report)
        cell = workbook["Successful"].cell(row=2, column=STATEMENT_HEADERS.index("Remark") + 1)
        assert cell.data_type != "f"
        assert str(cell.value).startswith("'=")
        workbook.close()


class TestReconciliationSheets:
    """The follow-up list, which is the part that is painful to copy off a screen."""

    def test_bucket_rows_and_notes(self, make_statement_workbook, pm_input_df):
        buffer = make_statement_workbook(rows=[statement_row()])
        reconciled = build_statement_report([buffer], input_df=pm_input_df)
        workbook = _load(write_statement_workbook, reconciled)

        assert [cell.value for cell in workbook["Paid"][1]] == [
            "Phone",
            "Unique ID",
            "Input Amount",
            "Input Rows",
            "Successful",
            "Unsuccessful",
            "Paid Total",
            "Notes",
        ]
        missing = _rows(workbook["Missing from Statement"])[:-1]
        assert len(missing) > 0
        assert all(isinstance(row[0], int) for row in missing)  # phones as numbers
        workbook.close()

    def test_bucket_totals_the_paid_column(self, make_statement_workbook, pm_input_df):
        buffer = make_statement_workbook(rows=[statement_row()])
        reconciled = build_statement_report([buffer], input_df=pm_input_df)
        workbook = _load(write_statement_workbook, reconciled)
        worksheet = workbook["Paid"]
        total = _rows(worksheet)[-1]
        assert total[0] == "TOTAL"
        assert total[6] == 100.0  # the one successful payment
        workbook.close()


FINANCE_HEADERS = [
    "Approval Id",
    "Transaction Id",
    "Transaction Type",
    "Transaction Status",
    "Date",
    "Account Name",
    "Account Number",
    "Account Type",
    "Remark",
    "Initiated By",
    "Approved/Rejected By",
    "Amount",
    "Commission Amount",
    "Debit",
    "Credit",
    "Balance After",
]
STATUS = FINANCE_HEADERS.index("Transaction Status") + 1
PHONE = FINANCE_HEADERS.index("Account Number") + 1
REMARK = FINANCE_HEADERS.index("Remark") + 1
AMOUNT = FINANCE_HEADERS.index("Amount") + 1
COMMISSION = FINANCE_HEADERS.index("Commission Amount") + 1
DEBIT = FINANCE_HEADERS.index("Debit") + 1
CREDIT = FINANCE_HEADERS.index("Credit") + 1
BALANCE = FINANCE_HEADERS.index("Balance After") + 1


def _model_txn(status, is_successful, amount, remark=GOOD_REMARK, phone="254712345678"):
    """A transaction built as a model, so an amount survives on a failed row.

    `remark_parts` is parsed the way statement.py parses it, so these behave
    like transactions read from a real export.
    """
    return StatementTransaction(
        file_name="august.xlsx",
        row_number=2,
        status=status,
        is_successful=is_successful,
        date_raw=GOOD_DATE,
        account_name="TEST001",
        account_number=phone,
        remark=remark,
        remark_parts=parse_case_remark(remark)[0],
        amount=amount,
    )


class TestFinanceWorkbook:
    """The sheet finance posts from: one Debit column, failures shaded not dropped."""

    def test_single_sheet_with_ledger_columns(self, report):
        workbook = _load(write_finance_workbook, report)
        assert workbook.sheetnames == ["Finance Reconciliation"]
        assert [cell.value for cell in workbook.active[1]] == FINANCE_HEADERS
        workbook.close()

    def test_statement_fields_carried_across(self, report):
        workbook = _load(write_finance_workbook, report)
        row = _rows(workbook.active)[0]
        assert row[: FINANCE_HEADERS.index("Amount")] == (
            "14886185",
            "18488654",
            "Payment",
            "Successful",
            GOOD_DATE,
            "9019830",
            254712345678,
            "Partner",
            GOOD_REMARK,
            "Test User",
            "Test Approver",
        )
        workbook.close()

    def test_successful_row_carries_its_amount_as_debit(self, report):
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        assert worksheet.cell(row=2, column=DEBIT).value == 100
        assert worksheet.cell(row=2, column=AMOUNT).value == 100
        assert worksheet.cell(row=2, column=STATUS).value == "Successful"
        workbook.close()

    def test_reversed_row_is_shaded_with_no_debit(self, report):
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        reversed_row = next(
            row for row in range(2, worksheet.max_row + 1)
            if worksheet.cell(row=row, column=STATUS).value == "Reversed"
        )
        assert worksheet.cell(row=reversed_row, column=DEBIT).value is None
        assert worksheet.cell(row=reversed_row, column=1).fill.start_color.rgb == "00FFC7CE"
        workbook.close()

    def test_total_is_the_debit_column_only(self, report):
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        total_row = worksheet.max_row
        assert worksheet.cell(row=total_row, column=1).value == "TOTAL"
        assert worksheet.cell(row=total_row, column=DEBIT).value == 350.0  # 100 + 250
        assert worksheet.cell(row=total_row, column=DEBIT).font.bold
        assert worksheet.cell(row=total_row, column=DEBIT).number_format == "#,##0"
        # "they only want the total for Debit" — nothing else is totalled
        for column in range(2, len(FINANCE_HEADERS) + 1):
            if column != DEBIT:
                assert worksheet.cell(row=total_row, column=column).value in ("", None)
        workbook.close()

    def test_failed_row_with_an_amount_is_excluded(self):
        """The reason Debit keys off is_successful, not off a missing amount.

        A Reversed row happens to arrive with no amount; a Failed one need not,
        and it is still not money that left the float. Amount still shows it.
        """
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 400.0),
                _model_txn("Failed", False, 600.0, phone="254798765432"),
            ]
        )
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        assert worksheet.cell(row=3, column=STATUS).value == "Failed"
        assert worksheet.cell(row=3, column=AMOUNT).value == 600.0
        assert worksheet.cell(row=3, column=DEBIT).value is None
        assert worksheet.cell(row=3, column=1).fill.start_color.rgb == "00FFC7CE"
        assert worksheet.cell(row=worksheet.max_row, column=DEBIT).value == 400.0
        workbook.close()

    def test_remark_written_in_full(self):
        """The whole reference, not just the case number, and verbatim when unparsed."""
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 100.0),
                _model_txn("Successful", True, 100.0, remark="no case here"),
            ]
        )
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        assert worksheet.cell(row=2, column=REMARK).value == GOOD_REMARK
        assert worksheet.cell(row=3, column=REMARK).value == "no case here"
        workbook.close()

    def test_optional_columns_blank_when_export_lacks_them(self, report):
        workbook = _load(write_finance_workbook, report)
        worksheet = workbook.active
        for column in (COMMISSION, CREDIT, BALANCE):
            assert worksheet.cell(row=2, column=column).value is None
        workbook.close()

    def test_optional_columns_carried_when_present(self, make_statement_workbook):
        """An export that carries Commission/Credit/Balance After passes them through."""
        buffer = make_statement_workbook(
            rows=[
                statement_row(
                    **{"Commission Amount": 2, "Credit": 0, "Balance After": 9900}
                )
            ],
            extra_columns=["Commission Amount", "Credit", "Balance After"],
        )
        workbook = _load(write_finance_workbook, build_statement_report([buffer]))
        worksheet = workbook.active
        assert worksheet.cell(row=2, column=COMMISSION).value == 2
        assert worksheet.cell(row=2, column=CREDIT).value == 0
        assert worksheet.cell(row=2, column=BALANCE).value == 9900
        assert worksheet.cell(row=2, column=BALANCE).number_format == "#,##0"
        workbook.close()

    def test_phone_written_as_a_number(self, report):
        workbook = _load(write_finance_workbook, report)
        cell = workbook.active.cell(row=2, column=PHONE)
        assert cell.value == 254712345678
        assert cell.number_format == "0"
        workbook.close()

    def test_no_transactions_means_no_total_row(self):
        workbook = _load(write_finance_workbook, StatementReport())
        assert workbook.active.max_row == 1
        workbook.close()


OTHER_REMARK = "C#37181 22505AA RESP AIRTIME-KSH500 d05"


class TestRemarkFileStem:
    """Both statement downloads are named after the Remark, since they are filed by case."""

    def test_single_remark_names_the_file(self):
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 100.0),
                _model_txn("Failed", False, 100.0, phone="254798765432"),
            ]
        )
        assert remark_file_stem(report) == GOOD_REMARK

    def test_several_cases_join_their_numbers_in_order(self):
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 100.0),
                _model_txn("Successful", True, 100.0, remark=OTHER_REMARK),
                _model_txn("Successful", True, 100.0),
            ]
        )
        assert remark_file_stem(report) == "C#37154_C#37181"

    def test_unparsed_remarks_are_skipped_when_joining(self):
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 100.0),
                _model_txn("Successful", True, 100.0, remark="no case here"),
            ]
        )
        assert remark_file_stem(report) == "C#37154"

    def test_nothing_usable_means_none(self):
        report = StatementReport(
            transactions=[
                _model_txn("Successful", True, 100.0, remark="first"),
                _model_txn("Successful", True, 100.0, remark="second"),
            ]
        )
        assert remark_file_stem(report) is None
        assert remark_file_stem(StatementReport()) is None

    def test_unsafe_file_name_characters_replaced(self):
        report = StatementReport(
            transactions=[_model_txn("Successful", True, 100.0, remark='case 12/3: "x"?.')]
        )
        assert remark_file_stem(report) == "case 12_3_ _x__"
