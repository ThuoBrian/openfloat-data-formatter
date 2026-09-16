"""Configuration for the OpenFloat Data Formatter.

All tuneable values are defined here with sensible defaults.
Override via environment variables or a .env file.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Default template path relative to project root
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "docs" / "openfloat-transactions-template.xlsx"

# Process Maker → OpenFloat network mapping
DEFAULT_NETWORK_MAP: dict[str, str] = {
    "Safaricom": "Safaricom Prepaid",
    "Airtel": "Airtel Prepaid",
    "Airtel Postpaid": "Airtel Postpaid",
    "Telkom": "Telkom Kenya Prepaid",
    "Telkom Postpaid": "Telkom Kenya Postpaid",
}

# OpenFloat Accounts sheet column order
OPENFLOAT_ACCOUNTS_COLUMNS = [
    "Account Type",
    "Account Name",
    "Account Number",
    "Till or Paybill Number",
    "Till or Paybill Business Name",
    "Notification Phone Number",
    "Amount",
    "Remark",
]

# Input columns that can carry the identifier written to the output
# 'Account Name'. Projects name this column differently (a staff airtime run
# has 'Staff ID', a respondent run has 'Respondent ID', and so on), so the
# column is matched by any of these names — case-insensitively and ignoring
# spaces, underscores and hyphens. First one present with a value wins.
ACCOUNT_NAME_COLUMNS = (
    "unique_id",
    "staff_id",
    "respondent_id",
    "case_id",
    "reso_id",
)

# Vocabulary for detecting that column by shape rather than by exact name, so a
# header nobody thought to list ('Staff', 'respo', 'Beneficiary Ref') still
# resolves. See normalizer.py::find_account_name_column for the scoring.
#
# EXCLUDE is the load-bearing part: without it 'Staff Name' beats 'Staff ID',
# and 'case_remark' (which contains the keyword 'case') wins on our own template.
ACCOUNT_NAME_EXCLUDE_TOKENS = (
    "name",
    "phone",
    "network",
    "amount",
    "date",
    "remark",
    "project",
    "department",
    "survey",
    "consent",
    "activity",
    "today",
)
ACCOUNT_NAME_KEYWORDS = (
    "unique",
    "staff",
    "resp",
    "case",
    "reso",
    "beneficiary",
    "participant",
    "enumerator",
)
ACCOUNT_NAME_ID_TOKENS = ("id", "number", "ref", "code")

# Process Maker input columns
PROCESSMAKER_COLUMNS = [
    "unique_id",
    "airtime_phone",
    "network",
    "submissiondate",
    "today",
    "amount",
    "project_name",
    "Project_Activity",
    "department",
    "survey",
]


class Settings(BaseSettings):
    """Application settings. Override via environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Validation thresholds
    max_amount_threshold: int = 10_000
    default_country_prefix: str = "254"

    # Explicit identifier column for the output 'Account Name'. None = detect it
    # (the UI picker sets this per upload; ACCOUNT_NAME_COLUMN overrides via env).
    account_name_column: str | None = None

    # File paths
    openfloat_template_path: str = str(DEFAULT_TEMPLATE_PATH)

    # Network mapping (not typically overridden via env)
    network_map: dict[str, str] = DEFAULT_NETWORK_MAP


# Singleton settings instance
settings = Settings()
