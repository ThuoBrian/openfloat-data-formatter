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

# Process Maker input columns
PROCESSMAKER_COLUMNS = [
    "unique_id",
    "consent",
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
    required_consent_value: str = "Yes"

    # File paths
    openfloat_template_path: str = str(DEFAULT_TEMPLATE_PATH)

    # Network mapping (not typically overridden via env)
    network_map: dict[str, str] = DEFAULT_NETWORK_MAP


# Singleton settings instance
settings = Settings()
