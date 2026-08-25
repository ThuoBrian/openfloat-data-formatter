"""Tests for the mapper module — network to account type mapping."""

import pytest

from backend.mapper import map_network
from backend.config import DEFAULT_NETWORK_MAP


class TestMapNetwork:
    """Test network mapping per golden prompt §4.1."""

    @pytest.mark.parametrize(
        "network,expected",
        [
            ("Safaricom", "Safaricom Prepaid"),
            ("Airtel", "Airtel Prepaid"),
            ("Airtel Postpaid", "Airtel Postpaid"),
            ("Telkom", "Telkom Kenya Prepaid"),
            ("Telkom Postpaid", "Telkom Kenya Postpaid"),
        ],
    )
    def test_known_mappings(self, network, expected):
        """All 5 known network mappings produce correct account types."""
        result, error = map_network(network)
        assert result == expected
        assert error is None

    def test_unmapped_network(self):
        """Unrecognized network returns an error."""
        result, error = map_network("Orange")
        assert result == ""
        assert "Unrecognized" in error
        assert "Orange" in error

    def test_empty_network(self):
        """Empty string network returns an error."""
        result, error = map_network("")
        assert result == ""
        assert error is not None

    def test_case_sensitivity(self):
        """Mapping is case-sensitive per the spec (exact match)."""
        result, error = map_network("safaricom")  # lowercase
        assert result == ""
        assert error is not None

    def test_custom_mapping(self):
        """Custom network map override works."""
        custom_map = {"TestNet": "Test Type"}
        result, error = map_network("TestNet", network_map=custom_map)
        assert result == "Test Type"
        assert error is None

    def test_custom_mapping_unmapped(self):
        """Custom map doesn't fall back to default for unmapped networks."""
        custom_map = {"TestNet": "Test Type"}
        result, error = map_network("Safaricom", network_map=custom_map)
        assert result == ""
        assert error is not None