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
    # Some exports write the carrier's full name. Prepaid, matching how bare
    # "Airtel" maps — a postpaid line is always spelled out as such.
    "Airtel Kenya": "Airtel Prepaid",
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

# Input columns that can carry the project code used in the output Remark's case
# reference. A plain tolerant alias match, deliberately not the fuzzy scoring
# above: `project_name` sits next to it in every export and is not a code.
PROJECT_CODE_COLUMNS = (
    "project_code",
    "award_code",
    "proj_code",
    "project_number",
)

# Input columns whose header changes between exports. Only the identifier
# column was flexible before; a run naming its phone column 'payphone_number'
# or its network column 'service_provider' failed every row against a column
# that was not there. Each canonical field lists the headers seen in real
# Process Maker runs; matching ignores case, spaces, underscores and hyphens
# (see normalizer.py::resolve_input_columns).
INPUT_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "airtime_phone": (
        "airtime_phone",
        "payphone_number",
        "pay_phone",
        "payment_phone",
        "phone",
        "phone_number",
        "mobile",
        "mobile_number",
        "msisdn",
        "telephone",
        "recipient_phone",
        "beneficiary_phone",
        "beneficiary_contact",
        "contact_number",
        "mpesa_number",
        "airtime_no",
        "tel",
        "cell",
    ),
    "network": (
        "network",
        "service_provider",
        "provider",
        "telco",
        "carrier",
        "mobile_network",
        "network_provider",
        "operator",
        "mno",
    ),
    "amount": (
        "amount",
        "airtime_amount",
        "pay_amount",
        "payment_amount",
        "amount_kes",
        "value",
        "kes",
    ),
    "case_remark": (
        "case_remark",
        "remark",
        "case_reference",
        "case_ref",
    ),
    "project_name": (
        "project_name",
        "current_project",
        "project",
    ),
    "Project_Activity": (
        "Project_Activity",
        "activity",
    ),
}

# Last-resort token match for the three fields whose absence fails every row.
# Applied only when no alias matched, so an unlisted header like
# 'respondent_mobile_no' still resolves. Deliberately not offered for the
# Remark or project columns, where a wrong guess writes a bad reference
# rather than simply failing loudly.
INPUT_COLUMN_TOKENS: dict[str, tuple[str, ...]] = {
    "airtime_phone": ("phone", "msisdn", "mobile"),
    "network": ("network", "provider", "telco", "carrier"),
    "amount": ("amount",),
}

# Headers a token match must never claim, per field. 'date' is excluded
# everywhere ('paydate' is not an amount). 'name' is excluded only for the
# fields where it signals a person rather than the value: 'phone_owner_name'
# is not a phone, but 'network_name' and 'provider_name' genuinely are the
# network — a blanket exclusion here silently dropped three of the commonest
# network headers.
INPUT_COLUMN_TOKEN_EXCLUDE: dict[str, tuple[str, ...]] = {
    "airtime_phone": ("name", "date"),
    "network": ("date",),
    "amount": ("name", "date"),
}

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

    # Project code for the Remark's case reference, used when the export has no
    # project-code column of its own. Set per upload in the app, or via
    # PROJECT_CODE in the environment.
    project_code: str | None = None

    # File paths
    openfloat_template_path: str = str(DEFAULT_TEMPLATE_PATH)

    # Network mapping (not typically overridden via env)
    network_map: dict[str, str] = DEFAULT_NETWORK_MAP


# Singleton settings instance
settings = Settings()
