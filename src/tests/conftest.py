"""Shared test fixtures for the OpenFloat Data Formatter test suite."""

from pathlib import Path

import pandas as pd
import pytest

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Reference data paths
SAMPLE_CSV_PATH = PROJECT_ROOT / "docs" / "1_ProcessMaker_Bridges_Combined_Airtime_Report.csv"
TEMPLATE_PATH = PROJECT_ROOT / "docs" / "openfloat-transactions-template.xlsx"

# Add src to path for imports
import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))


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
    from backend.config import Settings

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