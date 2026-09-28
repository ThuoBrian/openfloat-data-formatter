"""Tests for the config module — Settings validation."""

import pytest
from pydantic import ValidationError

from openfloat_formatter.config import Settings


class TestCountryPrefix:
    """A bad prefix would rewrite every phone number in a batch, so it is refused."""

    @pytest.mark.parametrize("prefix", ["254", "1", "44"])
    def test_digit_codes_accepted(self, prefix):
        assert Settings(default_country_prefix=prefix).default_country_prefix == prefix

    @pytest.mark.parametrize("prefix", ["", "+254", "25a", "2544", " 254"])
    def test_anything_else_rejected(self, prefix):
        with pytest.raises(ValidationError):
            Settings(default_country_prefix=prefix)

    def test_env_value_is_checked_too(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_COUNTRY_PREFIX", "+254")
        with pytest.raises(ValidationError):
            Settings()
