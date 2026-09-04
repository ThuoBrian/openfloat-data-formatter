"""Pydantic data models for the OpenFloat Data Formatter.

These models define the data contracts for:
- Output rows (OpenFloat template)
- Validation results (errors and warnings)
- Transformation results
- Statement reports (parsing, summaries, reconciliation)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Any

from pydantic import BaseModel, Field

from .normalizer import CaseRemarkParts


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IssueSeverity(str, Enum):
    """Severity of a validation issue."""

    ERROR = "error"  # Row is excluded from output
    WARNING = "warning"  # Row is included but flagged


# ---------------------------------------------------------------------------
# Output Row Model
# ---------------------------------------------------------------------------


class OutputRow(BaseModel):
    """A single row formatted for the OpenFloat Accounts sheet."""

    account_type: str = Field(alias="Account Type")
    account_name: str = Field(alias="Account Name")
    account_number: str = Field(alias="Account Number")
    till_or_paybill_number: str = Field(default="", alias="Till or Paybill Number")
    till_or_paybill_business_name: str = Field(
        default="", alias="Till or Paybill Business Name"
    )
    notification_phone_number: str = Field(alias="Notification Phone Number")
    amount: float = Field(alias="Amount")
    remark: str = Field(default="", alias="Remark")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Validation Models
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single validation issue found in an input row."""

    row_number: int
    severity: IssueSeverity
    field: str
    message: str


class FilteredCounts(BaseModel):
    """Count of rows filtered out by each validation rule."""

    consent_filtered: int = 0
    invalid_phone: int = 0
    invalid_amount: int = 0
    unmapped_network: int = 0


class ValidationReport(BaseModel):
    """Complete validation report for an input file."""

    total_rows: int = 0
    valid_rows: int = 0
    filtered_counts: FilteredCounts = Field(default_factory=FilteredCounts)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Transform Result
# ---------------------------------------------------------------------------


class TransformResult(BaseModel):
    """Result of the full transformation pipeline."""

    output: BytesIO | None = None
    validation_report: ValidationReport = Field(default_factory=ValidationReport)
    output_row_count: int = 0

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Statement Report Models
#
# These model OpenFloat 'Transaction Statement' exports — the reports the SaaS
# produces AFTER a disbursement batch — and the reconciliation of those
# statements against the original Process Maker input.
# ---------------------------------------------------------------------------


class StatementTransaction(BaseModel):
    """One parsed row of an OpenFloat 'Transaction Statement' export."""

    file_name: str = ""
    row_number: int = 0  # Excel row number, 1-based (header = row 1)
    approval_id: str = ""
    transaction_id: str = ""
    transaction_type: str = ""
    status: str = ""
    is_successful: bool = False  # status == "Successful" (case-insensitive)
    date_raw: str = ""  # original Date cell, kept verbatim
    date: datetime | None = None  # parsed; None on soft parse failure
    account_name: str = ""  # str-coerced (cells are ints or ids like 'I220008')
    account_number: str = ""  # normalized 254XXXXXXXXX; raw string if normalization failed
    account_number_error: str | None = None
    account_type: str = ""
    remark: str = ""
    remark_parts: CaseRemarkParts | None = None
    initiated_by: str = ""
    approved_rejected_by: str = ""
    reference_id: str = ""  # present on Reversed rows: original transaction id
    amount: float | None = None  # None on Reversed rows / empty cells


class StatementFileSummary(BaseModel):
    """Aggregate counts for one statement file (or the combined total)."""

    file_name: str = ""
    total_rows: int = 0  # data rows only (footer/blank rows excluded)
    successful_count: int = 0
    unsuccessful_count: int = 0
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    total_disbursed: float = 0.0  # sum of Successful amounts only
    footer_total: float | None = None  # grand-total cell in the footer row
    footer_matches: bool | None = None  # footer_total == total_disbursed; None if no footer
    success_rate: float = 0.0  # successful_count / total_rows; 0.0 when no rows
    unparsed_remarks: int = 0
    unparsed_dates: int = 0


class CaseRollup(BaseModel):
    """Per-case aggregation keyed by the parsed case_remark in the Remark column.

    The amount embedded in the remark (`AIRTIME-KSH<amount>`) is the per-case
    total, so `difference` (disbursed_total - remark_amount) is the meaningful
    shortfall/overage flag, not a per-row comparison.
    """

    case_number: str
    project_code: str
    activity_code: str
    remark_amount: float
    total_rows: int = 0
    successful_count: int = 0
    unsuccessful_count: int = 0
    disbursed_total: float = 0.0
    difference: float = 0.0


class ReconciliationEntry(BaseModel):
    """One beneficiary's reconciliation outcome (or a statement-only phone)."""

    phone: str
    unique_id: str = ""
    input_amount: float | None = None
    input_row_numbers: list[int] = Field(default_factory=list)  # Excel rows in the input df
    successful_count: int = 0  # Successful statement rows for this phone
    unsuccessful_count: int = 0
    successful_total: float = 0.0
    notes: list[str] = Field(default_factory=list)  # e.g. amount mismatch, phone error


class ReconciliationResult(BaseModel):
    """Outcome of matching a Process Maker input against statement transactions."""

    input_rows: int = 0
    matched_paid: list[ReconciliationEntry] = Field(default_factory=list)
    matched_not_paid: list[ReconciliationEntry] = Field(default_factory=list)
    missing_from_statement: list[ReconciliationEntry] = Field(default_factory=list)
    statement_not_in_input: list[ReconciliationEntry] = Field(default_factory=list)
    duplicate_input_phones: list[str] = Field(default_factory=list)
    multiply_paid_phones: list[str] = Field(default_factory=list)


class StatementReport(BaseModel):
    """Complete statement report: summaries, rollups, and optional reconciliation."""

    file_summaries: list[StatementFileSummary] = Field(default_factory=list)
    combined: StatementFileSummary = Field(default_factory=StatementFileSummary)
    transactions: list[StatementTransaction] = Field(default_factory=list)
    unsuccessful_transactions: list[StatementTransaction] = Field(default_factory=list)
    case_rollups: list[CaseRollup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # parse-level soft warnings
    errors: list[str] = Field(default_factory=list)  # structural per-file errors
    reconciliation: ReconciliationResult | None = None  # only when an input df was supplied