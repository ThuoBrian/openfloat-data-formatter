"""Pydantic data models for the OpenFloat Data Formatter.

These models define the data contracts for:
- Output rows (OpenFloat template)
- Validation results (errors and warnings)
- Transformation results
"""

from __future__ import annotations

from enum import Enum
from io import BytesIO
from typing import Any

from pydantic import BaseModel, Field


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