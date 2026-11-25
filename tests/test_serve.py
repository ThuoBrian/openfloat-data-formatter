"""Tests for the local launcher (serve.py) and the page FastAPI serves."""

import re
import sys

import pytest
from fastapi.testclient import TestClient

from openfloat_formatter import main, serve
from openfloat_formatter.main import WEB_DIR, app


@pytest.fixture
def client():
    return TestClient(app, base_url="http://127.0.0.1")


class TestThePage:
    """The built React page is served at / alongside the API."""

    def test_page_is_built_and_committed(self):
        """Staff never run Node, so the built page must ship in the repo."""
        assert (WEB_DIR / "index.html").is_file()

    def test_every_asset_the_page_names_exists(self):
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        assets = re.findall(r'(?:src|href)="/([^"]+)"', html)
        assert assets, "index.html names no assets"
        for asset in assets:
            assert (WEB_DIR / asset).is_file(), f"index.html names missing {asset}"

    def test_root_serves_the_page_fresh_and_locked_down(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "<div id=\"root\">" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["content-security-policy"] == main.CONTENT_SECURITY_POLICY
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_api_routes_win_over_the_page(self, client):
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/settings").json()["default_country_prefix"]

    def test_api_responses_carry_the_csp_too(self, client):
        assert "content-security-policy" in client.get("/health").headers

    def test_docs_are_exempt(self, client):
        """Swagger UI loads from a CDN; the CSP would leave /docs blank."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "content-security-policy" not in response.headers

    def test_foreign_host_cannot_load_the_page(self):
        foreign = TestClient(app, base_url="http://evil.example")
        assert foreign.get("/").status_code == 400


class TestLauncher:
    def test_nothing_listening_means_not_running(self, monkeypatch):
        monkeypatch.setattr(serve, "URL", "http://127.0.0.1:9/")  # discard port
        assert serve.already_running() is False

    def test_second_start_opens_the_running_copy(self, monkeypatch):
        opened: list[str] = []
        monkeypatch.setattr(serve, "already_running", lambda: True)
        monkeypatch.setattr(serve.webbrowser, "open", opened.append)
        monkeypatch.setattr(serve.uvicorn, "Server", lambda *_: pytest.fail("started a server"))

        serve.main()

        assert opened == [serve.URL]

    def test_bad_env_value_is_a_sentence_not_a_traceback(self, monkeypatch, capsys):
        monkeypatch.setattr(serve, "already_running", lambda: False)
        monkeypatch.setenv("DEFAULT_COUNTRY_PREFIX", "+254")
        # Force main.py to be imported afresh, so it reads the bad setting.
        monkeypatch.delitem(sys.modules, "openfloat_formatter.main")

        with pytest.raises(SystemExit) as exit_info:
            serve.main()

        assert exit_info.value.code == 1
        assert "settings file (.env" in capsys.readouterr().err
