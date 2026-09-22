"""Tests for canonical input-column resolution.

Exports rename their columns per run, so these cover the headers real runs
have used. Header names only — no real export is read here.
"""

import pandas as pd

from openfloat_formatter.config import Settings
from openfloat_formatter.normalizer import (
    canonicalize_input_columns,
    find_account_name_column,
    resolve_input_columns,
)
from openfloat_formatter.validator import validate


class TestResolveInputColumns:
    """Field → actual column resolution."""

    def test_canonical_headers_map_to_themselves(self):
        mapping, warnings = resolve_input_columns(
            ["unique_id", "airtime_phone", "network", "amount"]
        )
        assert mapping["airtime_phone"] == "airtime_phone"
        assert mapping["network"] == "network"
        assert mapping["amount"] == "amount"
        assert warnings == []

    def test_alias_headers(self):
        """The shape a real disbursement export used."""
        mapping, _ = resolve_input_columns(
            [
                "caseid",
                "payphone_number",
                "amount",
                "service_provider",
                "current_project",
                "Project_Activity",
                "department",
                "submissiondate",
                "paydate",
            ]
        )
        assert mapping["airtime_phone"] == "payphone_number"
        assert mapping["network"] == "service_provider"
        assert mapping["project_name"] == "current_project"
        assert mapping["amount"] == "amount"

    def test_alias_matching_ignores_case_and_separators(self):
        mapping, _ = resolve_input_columns(["Pay Phone Number", "Service-Provider"])
        assert mapping["airtime_phone"] == "Pay Phone Number"
        assert mapping["network"] == "Service-Provider"

    def test_canonical_name_beats_an_alias(self):
        """A file carrying both is read the documented way."""
        mapping, _ = resolve_input_columns(["airtime_phone", "mobile"])
        assert mapping["airtime_phone"] == "airtime_phone"

    def test_token_fallback_for_unlisted_header(self):
        mapping, warnings = resolve_input_columns(["respondent_mobile_no", "amount"])
        assert mapping["airtime_phone"] == "respondent_mobile_no"
        assert any("matched on shape" in w for w in warnings)

    def test_token_fallback_skips_name_and_date_headers(self):
        """'paydate' must not be read as a phone/amount column."""
        mapping, _ = resolve_input_columns(["phone_owner_name", "paydate"])
        assert "airtime_phone" not in mapping
        assert "amount" not in mapping

    def test_missing_field_is_absent_not_guessed(self):
        mapping, _ = resolve_input_columns(["caseid", "department"])
        assert "airtime_phone" not in mapping
        assert "network" not in mapping

    def test_one_column_claimed_by_one_field(self):
        mapping, _ = resolve_input_columns(["mobile", "phone"])
        assert len(set(mapping.values())) == len(mapping)

    def test_duplicate_aliases_warn(self):
        mapping, warnings = resolve_input_columns(["mobile", "msisdn", "amount"])
        assert mapping["airtime_phone"] == "mobile"
        assert any("all look like" in w for w in warnings)


class TestCanonicalizeInputColumns:
    """Frame-level renaming."""

    def test_frame_is_renamed_and_original_untouched(self):
        raw = pd.DataFrame(
            {"caseid": ["C1"], "payphone_number": [254785271309],
             "service_provider": ["Safaricom"], "amount": [100]}
        )
        df = canonicalize_input_columns(raw)
        assert "airtime_phone" in df.columns
        assert "network" in df.columns
        assert "payphone_number" in raw.columns  # caller's frame untouched

    def test_identifier_column_passes_through(self):
        """Renaming must not disturb Account Name detection."""
        raw = pd.DataFrame({"caseid": ["C1"], "payphone_number": [254785271309]})
        df = canonicalize_input_columns(raw)
        assert find_account_name_column(df.columns, None, frame=df) == "caseid"

    def test_renamed_file_validates(self):
        """The end of the bug: an aliased export produces valid rows."""
        raw = pd.DataFrame(
            {
                "caseid": ["C1", "C2"],
                "payphone_number": [254785271309, 254712345678],
                "service_provider": ["Safaricom", "Airtel"],
                "amount": [100, 200],
            }
        )
        df = canonicalize_input_columns(raw)
        report = validate(df, Settings())
        assert report.valid_rows == 2
        assert report.errors == []


class TestOverrides:
    """The escape hatch: the user names the column themselves."""

    def test_override_wins_over_detection(self):
        mapping, _ = resolve_input_columns(
            ["airtime_phone", "weird_col"], {"airtime_phone": "weird_col"}
        )
        assert mapping["airtime_phone"] == "weird_col"

    def test_override_resolves_a_header_no_alias_covers(self):
        """The whole point — an unlisted header works with no code change."""
        mapping, _ = resolve_input_columns(
            ["zzz_contact_field", "amount"], {"airtime_phone": "zzz_contact_field"}
        )
        assert mapping["airtime_phone"] == "zzz_contact_field"

    def test_override_matched_tolerantly(self):
        mapping, _ = resolve_input_columns(
            ["Pay Phone"], {"airtime_phone": "pay_phone"}
        )
        assert mapping["airtime_phone"] == "Pay Phone"

    def test_stale_override_falls_back_with_warning(self):
        mapping, warnings = resolve_input_columns(
            ["payphone_number"], {"airtime_phone": "gone_column"}
        )
        assert mapping["airtime_phone"] == "payphone_number"
        assert any("not in this file" in w for w in warnings)

    def test_override_does_not_let_two_fields_share_a_column(self):
        mapping, _ = resolve_input_columns(
            ["amount", "network"], {"airtime_phone": "amount"}
        )
        assert mapping["airtime_phone"] == "amount"
        assert mapping.get("amount") != "amount"

    def test_end_to_end_with_override(self):
        raw = pd.DataFrame(
            {
                "caseid": ["C1"],
                "zzz_contact": [254785271309],
                "zzz_telco": ["Safaricom"],
                "zzz_value": [100],
            }
        )
        df = canonicalize_input_columns(
            raw,
            {
                "airtime_phone": "zzz_contact",
                "network": "zzz_telco",
                "amount": "zzz_value",
            },
        )
        report = validate(df, Settings())
        assert report.valid_rows == 1


class TestNetworkNameHeaders:
    """'network_name' is the network; 'phone_owner_name' is a person."""

    def test_network_name_variants_resolve(self):
        for header in ("network_name", "provider_name", "telco_name"):
            mapping, _ = resolve_input_columns([header])
            assert mapping.get("network") == header, header

    def test_person_name_header_is_not_a_phone(self):
        mapping, _ = resolve_input_columns(["phone_owner_name"])
        assert "airtime_phone" not in mapping
