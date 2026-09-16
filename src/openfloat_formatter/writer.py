"""Excel output generation for the OpenFloat Data Formatter.

Two workbooks are written here.

`write_openfloat_excel` produces the upload itself, matching the OpenFloat
Transactions Template:
- Accounts: transformed data rows (phone columns written as numbers, not text)
- Allowed Types: verbatim copy from the reference template
The Allowed Types sheet must be copied exactly (including trailing spaces
like "SPA NAKURU RURAL ").

`write_finance_workbook` produces what finance posts: one Debit column holding
only money that actually moved, with the failures shaded rather than dropped.

`write_statement_workbook` produces the *report* on what happened afterwards:
Successful and Unsuccessful sheets, plus the reconciliation buckets when the
statement was matched against a Process Maker input. Every sheet ends in a bold
TOTAL row, the way OpenFloat's own statement export carries a grand total.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from io import BytesIO
from pathlib import Path
from typing import overload

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from .config import OPENFLOAT_ACCOUNTS_COLUMNS
from .models import OutputRow, ReconciliationEntry, StatementReport, StatementTransaction

# Leading characters that Excel/openpyxl treat as the start of a formula.
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")

# Account Number and Notification Phone Number go out as real numbers, not text:
# that is how OpenFloat stores them (its Transaction Statement export returns
# 254XXXXXXXXX as an int). "0" pins the display to plain digits — a 12-digit
# number under General format renders as 2.54713E+11 in a narrow column.
_PHONE_COLUMNS = ("Account Number", "Notification Phone Number")
_PHONE_NUMBER_FORMAT = "0"

# --- Statement report workbook -------------------------------------------------
# One row per statement transaction, in the export's own terms plus the file it
# came from — which is what tells rows apart once several statements are
# uploaded together.
_STATEMENT_COLUMNS = (
    "Source File",
    "Row",
    "Date",
    "Account Name",
    "Account Number",
    "Status",
    "Reference Id",
    "Remark",
    "Amount",
)
# One row per reconciled beneficiary; the bucket is the sheet name.
_RECONCILIATION_COLUMNS = (
    "Phone",
    "Unique ID",
    "Input Amount",
    "Input Rows",
    "Successful",
    "Unsuccessful",
    "Paid Total",
    "Notes",
)
_AMOUNT_NUMBER_FORMAT = "#,##0"
_TOTAL_LABEL = "TOTAL"

# --- Finance reconciliation workbook -------------------------------------------
# What finance posts: one Debit column holding only money that actually moved,
# with the failures left visible (shaded, Debit blank) as the evidence for why
# the total is not simply everything that was uploaded.
_FINANCE_COLUMNS = ("Date", "Account Name", "Phone", "Case", "Status", "Debit")
_FINANCE_SHEET = "Finance Reconciliation"
# Excel's own "Bad" styling. Chosen over a colour of our own because it still
# reads as flagged in greyscale, which a finance attachment often gets printed in.
_FLAGGED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
_FLAGGED_FONT = Font(color="9C0006")


def _as_phone_number(value: str) -> int | str:
    """Coerce a normalized phone string into an int for a Number-format cell.

    Falls back to the original string when the value is not a plain run of
    digits, or when it starts with a zero that int() would silently drop
    (reachable if `default_country_prefix` is set to something other than 254).
    """
    if value.isdigit() and not value.startswith("0"):
        return int(value)
    return value


def _sanitize_cell_value(value: object) -> object:
    """Neutralize spreadsheet formula injection in a string cell value.

    openpyxl auto-promotes any string starting with '=' (and Excel itself
    also treats a leading '+', '-', or '@' as a formula prefix) to a live
    formula cell. Since Account Name and Remark are built from free-typed
    user input (unique_id, case_remark), prefix such values with a single
    quote so they are written as plain text instead of executed on open.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return f"'{value}"
    return value


def _to_buffer(workbook: openpyxl.Workbook) -> BytesIO:
    """Save a workbook to an in-memory buffer, positioned for reading."""
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    workbook.close()
    return buffer


def load_allowed_types(template_path: str | Path) -> list[str]:
    """Load the Allowed Types list from the OpenFloat reference template.

    Reads column A of the 'Allowed Types' sheet, skipping the header row.
    Values are returned as-is to preserve exact strings (including trailing
    spaces like "SPA NAKURU RURAL ").

    Args:
        template_path: Path to the reference template .xlsx file.

    Returns:
        A list of allowed type strings.

    Raises:
        FileNotFoundError: If the template file does not exist.
        KeyError: If the 'Allowed Types' sheet is missing.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    wb = openpyxl.load_workbook(str(template_path), read_only=True, data_only=True)
    if "Allowed Types" not in wb.sheetnames:
        wb.close()
        raise KeyError(
            f"'Allowed Types' sheet not found in template. "
            f"Available sheets: {wb.sheetnames}"
        )

    ws = wb["Allowed Types"]
    types: list[str] = []
    for row in ws.iter_rows(min_row=1, max_col=1, values_only=True):
        value = row[0]
        if value is not None:
            # Preserve exact string including trailing spaces
            types.append(str(value))

    wb.close()
    return types


@overload
def write_openfloat_excel(
    rows: list[OutputRow], allowed_types: list[str], output_path: None = None
) -> BytesIO: ...

@overload
def write_openfloat_excel(
    rows: list[OutputRow], allowed_types: list[str], output_path: str | Path
) -> Path: ...

def write_openfloat_excel(
    rows: list[OutputRow],
    allowed_types: list[str],
    output_path: str | Path | None = None,
) -> BytesIO | Path:
    """Write a two-sheet OpenFloat-ready Excel file.

    Args:
        rows: List of OutputRow objects for the Accounts sheet.
        allowed_types: List of allowed type strings for the Allowed Types sheet.
        output_path: If provided, writes to this file path. If None, returns BytesIO.

    Returns:
        BytesIO containing the .xlsx if output_path is None,
        otherwise the Path of the written file.
    """
    # Create workbook
    wb = openpyxl.Workbook()

    # --- Accounts sheet ---
    ws_accounts = wb.active
    ws_accounts.title = "Accounts"

    # Write header row
    ws_accounts.append(OPENFLOAT_ACCOUNTS_COLUMNS)

    # Write data rows
    phone_columns = [OPENFLOAT_ACCOUNTS_COLUMNS.index(name) + 1 for name in _PHONE_COLUMNS]
    for row in rows:
        ws_accounts.append([
            _sanitize_cell_value(row.account_type),
            _sanitize_cell_value(row.account_name),
            _as_phone_number(row.account_number),
            _sanitize_cell_value(row.till_or_paybill_number),
            _sanitize_cell_value(row.till_or_paybill_business_name),
            _as_phone_number(row.notification_phone_number),
            row.amount,
            _sanitize_cell_value(row.remark),
        ])
        for col in phone_columns:
            cell = ws_accounts.cell(row=ws_accounts.max_row, column=col)
            if isinstance(cell.value, int):
                cell.number_format = _PHONE_NUMBER_FORMAT

    # --- Allowed Types sheet ---
    ws_types = wb.create_sheet(title="Allowed Types")

    # Write each type as a single-cell row (column A only)
    for type_name in allowed_types:
        ws_types.append([type_name])

    # Save to BytesIO or file
    if output_path is not None:
        output_path = Path(output_path)
        wb.save(str(output_path))
        wb.close()
        return output_path
    return _to_buffer(wb)


def _column_total(rows: Sequence[Sequence[object]], index: int) -> float:
    """Sum one column across rows, skipping blanks (a Reversed row has no Amount)."""
    total = 0.0
    for row in rows:
        value = row[index]
        if isinstance(value, int | float):
            total += float(value)
    return total


def _write_sheet(
    worksheet: Worksheet,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    amount_columns: Sequence[str] = (),
    phone_columns: Sequence[str] = (),
    flag_row: Callable[[Sequence[object]], bool] | None = None,
) -> None:
    """Write one sheet: bold header, the rows, then a bold TOTAL row.

    Free text is sanitized on the way in — these values come from a file
    someone else produced, which is exactly what `_sanitize_cell_value` guards.
    An empty sheet gets its header and no TOTAL row: there is nothing to sum,
    and a bold zero reads like a finding.

    Args:
        flag_row: Optional predicate; rows it returns True for are shaded as
            needing attention, without changing what they contribute to a total.
    """
    header_font = Font(bold=True)
    worksheet.append(list(columns))
    for index, column in enumerate(columns, start=1):
        cell = worksheet.cell(row=1, column=index)
        cell.font = header_font
        worksheet.column_dimensions[cell.column_letter].width = max(12, len(column) + 2)
    worksheet.freeze_panes = "A2"

    amount_indexes = [columns.index(name) + 1 for name in amount_columns]
    phone_indexes = [columns.index(name) + 1 for name in phone_columns]

    for row in rows:
        worksheet.append([_sanitize_cell_value(value) for value in row])
        for index in amount_indexes:
            cell = worksheet.cell(row=worksheet.max_row, column=index)
            if isinstance(cell.value, int | float):
                cell.number_format = _AMOUNT_NUMBER_FORMAT
        for index in phone_indexes:
            cell = worksheet.cell(row=worksheet.max_row, column=index)
            if isinstance(cell.value, int):
                cell.number_format = _PHONE_NUMBER_FORMAT
        if flag_row is not None and flag_row(row):
            for index in range(1, len(columns) + 1):
                cell = worksheet.cell(row=worksheet.max_row, column=index)
                cell.fill = _FLAGGED_FILL
                cell.font = _FLAGGED_FONT

    if not rows:
        return

    total_row: list[object] = [""] * len(columns)
    total_row[0] = _TOTAL_LABEL
    for name in amount_columns:
        index = columns.index(name)
        total_row[index] = _column_total(rows, index)
    worksheet.append(total_row)
    for index in range(1, len(columns) + 1):
        cell = worksheet.cell(row=worksheet.max_row, column=index)
        cell.font = header_font
        if index in amount_indexes:
            cell.number_format = _AMOUNT_NUMBER_FORMAT


def _statement_rows(transactions: Sequence[StatementTransaction]) -> list[list[object]]:
    """Statement transactions as sheet rows, in `_STATEMENT_COLUMNS` order."""
    return [
        [
            transaction.file_name,
            transaction.row_number,
            transaction.date_raw,  # as the export wrote it, not a reformatted date
            transaction.account_name,
            _as_phone_number(transaction.account_number),
            transaction.status,
            transaction.reference_id,
            transaction.remark,
            transaction.amount,  # None on a Reversed row -> blank cell
        ]
        for transaction in transactions
    ]


def _reconciliation_rows(entries: Sequence[ReconciliationEntry]) -> list[list[object]]:
    """Reconciliation entries as sheet rows, in `_RECONCILIATION_COLUMNS` order."""
    return [
        [
            _as_phone_number(entry.phone),
            entry.unique_id,
            entry.input_amount,
            ", ".join(str(number) for number in entry.input_row_numbers),
            entry.successful_count,
            entry.unsuccessful_count,
            entry.successful_total,
            "; ".join(entry.notes),
        ]
        for entry in entries
    ]


def write_statement_workbook(report: StatementReport) -> BytesIO:
    """Write the Statement Report as a downloadable .xlsx.

    Sheets: Successful, Unsuccessful (which is where Reversed rows land), and —
    only when the report was reconciled against a Process Maker input — the four
    reconciliation buckets. Each sheet ends in a bold TOTAL row over its amount
    columns.

    Args:
        report: The report to write, from `statement.build_statement_report`.

    Returns:
        A BytesIO positioned at 0, ready for `st.download_button`.
    """
    workbook = openpyxl.Workbook()

    successful = [
        transaction for transaction in report.transactions if transaction.is_successful
    ]
    sheet = workbook.active
    sheet.title = "Successful"
    _write_sheet(
        sheet,
        _STATEMENT_COLUMNS,
        _statement_rows(successful),
        amount_columns=("Amount",),
        phone_columns=("Account Number",),
    )
    _write_sheet(
        workbook.create_sheet("Unsuccessful"),
        _STATEMENT_COLUMNS,
        _statement_rows(report.unsuccessful_transactions),
        amount_columns=("Amount",),
        phone_columns=("Account Number",),
    )

    if report.reconciliation is not None:
        buckets = (
            ("Paid", report.reconciliation.matched_paid),
            ("Matched but Unpaid", report.reconciliation.matched_not_paid),
            ("Missing from Statement", report.reconciliation.missing_from_statement),
            ("Not in Input", report.reconciliation.statement_not_in_input),
        )
        for title, entries in buckets:
            _write_sheet(
                workbook.create_sheet(title),
                _RECONCILIATION_COLUMNS,
                _reconciliation_rows(entries),
                amount_columns=("Input Amount", "Paid Total"),
                phone_columns=("Phone",),
            )

    return _to_buffer(workbook)


def _case_reference(transaction: StatementTransaction) -> str:
    """The case this payment belongs to, as finance would cite it."""
    if transaction.remark_parts is not None:
        return f"C#{transaction.remark_parts.case_number}"
    return transaction.remark


def _finance_rows(transactions: Sequence[StatementTransaction]) -> list[list[object]]:
    """Statement transactions as finance rows, in `_FINANCE_COLUMNS` order.

    Debit is filled **only** for a successful transaction. Keying off
    `is_successful` rather than off a present amount is the whole point: a
    Reversed row happens to arrive with no amount, but a Failed or Pending one
    need not, and none of them are money that left the float.
    """
    return [
        [
            transaction.date_raw,
            transaction.account_name,
            _as_phone_number(transaction.account_number),
            _case_reference(transaction),
            transaction.status,
            transaction.amount if transaction.is_successful else None,
        ]
        for transaction in transactions
    ]


def write_finance_workbook(report: StatementReport) -> BytesIO:
    """Write the finance reconciliation sheet as a downloadable .xlsx.

    One sheet, every transaction in statement order. Unsuccessful rows are
    shaded and leave Debit empty, so the single TOTAL under Debit is exactly
    the amount that left the float — while the failures stay on the page as
    the evidence for why it is not simply everything that was uploaded.

    Args:
        report: The report to write, from `statement.build_statement_report`.

    Returns:
        A BytesIO positioned at 0, ready for `st.download_button`.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = _FINANCE_SHEET

    rows = _finance_rows(report.transactions)
    debit_index = _FINANCE_COLUMNS.index("Debit")
    _write_sheet(
        sheet,
        _FINANCE_COLUMNS,
        rows,
        amount_columns=("Debit",),
        phone_columns=("Phone",),
        flag_row=lambda row: row[debit_index] is None,
    )
    return _to_buffer(workbook)
