"""Shared test fixtures for the OpenFloat Data Formatter test suite."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Reference data paths
SAMPLE_CSV_PATH = PROJECT_ROOT / "docs" / "1_ProcessMaker_Bridges_Combined_Airtime_Report.csv"
TEMPLATE_PATH = PROJECT_ROOT / "docs" / "openfloat-transactions-template.xlsx"


@pytest.fixture
def sample_csv_path():
    """Path to the sample Process Maker CSV file.

    This file is not committed to the repo (see CLAUDE.md's "Reference Data
    in docs/" table) — tests depending on it skip rather than error when it's
    absent, instead of failing on every fresh clone.
    """
    if not SAMPLE_CSV_PATH.exists():
        pytest.skip(f"Sample CSV not found at {SAMPLE_CSV_PATH} — see CLAUDE.md")
    return SAMPLE_CSV_PATH


@pytest.fixture
def template_path():
    """Path to the OpenFloat reference template."""
    assert TEMPLATE_PATH.exists(), f"Template not found at {TEMPLATE_PATH}"
    return TEMPLATE_PATH


@pytest.fixture
def sample_df(sample_csv_path):
    """DataFrame loaded from the sample Process Maker CSV."""
    return pd.read_csv(sample_csv_path)


@pytest.fixture
def default_config():
    """Default Settings instance for testing."""
    from openfloat_formatter.config import Settings

    return Settings(
        max_amount_threshold=10_000,
        default_country_prefix="254",
        required_consent_value="Yes",
        openfloat_template_path=str(TEMPLATE_PATH),
    )


@pytest.fixture
def minimal_df():
    """Minimal valid DataFrame for targeted tests."""
    return pd.DataFrame(
        {
            "unique_id": ["TEST001", "TEST002"],
            "consent": ["Yes", "Yes"],
            "airtime_phone": ["712345678", "798765432"],
            "network": ["Safaricom", "Airtel"],
            "submissiondate": ["8/25/2026 10:00", "8/25/2026 11:00"],
            "today": ["25aug2026", "25aug2026"],
            "amount": [150, 200],
            "project_name": ["Test Project", "Test Project"],
            "Project_Activity": ["g05|Testing", "g05|Testing"],
            "department": ["Projects", "Projects"],
            "survey": ["Baseline", "Baseline"],
        }
    )


# ---------------------------------------------------------------------------
# Statement report fixtures
#
# The real statement exports in sample_report_output/ contain personal data
# (phone numbers, staff names) and are NOT tracked by git. All statement tests
# therefore build SYNTHETIC workbooks in memory — never reference the real
# files from the test suite.
# ---------------------------------------------------------------------------

STATEMENT_HEADER_BASE = [
    "Approval Id",
    "Transaction Id",
    "Transaction Status",
    "Date",
    "Account Name",
    "Account Number",
    "Account Type",
    "Remark",
    "Initiated By",
    "Approved/Rejected By",
]


@pytest.fixture
def make_statement_workbook():
    """Factory fixture: build a synthetic Transaction Statement .xlsx in memory.

    Args (via the factory call):
        rows: list of dicts keyed by header name (missing keys become None).
        include_reference_id: True → 13-column header (with 'Reference Id',
            matching the C#37154-style export), False → 12-column header
            (matching the C#37181-style export).
        footer_total: appends the grand-total footer row when not None.
        sheet_name: sheet title (defaults to 'Transaction Statement').

    Returns a BytesIO ready for parse_statement_file / build_statement_report.
    """

    def _make(
        rows=None,
        include_reference_id=True,
        footer_total=None,
        sheet_name="Transaction Statement",
    ):
        header = list(STATEMENT_HEADER_BASE)
        # The real header order puts 'Transaction Type' after 'Transaction Id'
        header.insert(2, "Transaction Type")
        if include_reference_id:
            header.append("Reference Id")
        header.append("Amount")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name
        worksheet.append(header)
        for row in rows or []:
            worksheet.append([row.get(column, None) for column in header])
        if footer_total is not None:
            worksheet.append([None] * (len(header) - 1) + [footer_total])

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return buffer

    return _make


@pytest.fixture
def pm_input_df():
    """Synthetic Process Maker input hitting every reconciliation bucket.

    Statement side (build with make_statement_workbook, see test_statement.py):
    - 254712345678: one Successful row of 100  → matched_paid, clean amount
    - 254722345678: one Reversed row only      → matched_not_paid
    - 254742345678: Successful row of 50        → matched_paid, amount mismatch
    - 254752345678: two Successful rows of 100  → duplicate pair, multiply paid
    - 254733345678: absent from the statement  → missing_from_statement
    """
    rows = []
    for phone in ("712345678", "722345678", "742345678", "752345678", "752345678", "733345678"):
        rows.append(
            {
                "unique_id": f"TEST{len(rows) + 1:03d}",
                "consent": "Yes",
                "airtime_phone": phone,
                "network": "Safaricom",
                "submissiondate": "8/25/2026 10:00",
                "today": "25aug2026",
                "amount": 100,
                "project_name": "Test Project",
                "Project_Activity": "g05|Testing",
                "department": "Projects",
                "survey": "Baseline",
            }
        )
    return pd.DataFrame(rows)