"""Tests for the FastAPI layer — endpoints in openfloat_formatter.main."""

import io
import signal
import threading
from urllib.parse import quote

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from openfloat_formatter import main
from openfloat_formatter.main import app

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# What the app's own page sends: a localhost Host, and the client header every
# POST must carry (see main.py's browser-protection block).
LOCAL_BASE_URL = "http://127.0.0.1"
CLIENT_HEADERS = {main.CLIENT_HEADER: "1"}


@pytest.fixture
def client():
    """TestClient for the FastAPI app, talking to it the way the app's page does."""
    return TestClient(app, base_url=LOCAL_BASE_URL, headers=CLIENT_HEADERS)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to CSV bytes for multipart upload."""
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer.getvalue()


class TestHealth:
    """GET /health."""

    def test_returns_ok(self, client):
        """The health check reports ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestNoCors:
    """No browser origin is allowed to call the API."""

    def test_no_allow_origin_header(self, client):
        """A wildcard origin would let any web page post files to localhost."""
        response = client.get("/health", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" not in response.headers


class TestUploadSizeLimit:
    """Oversized uploads are refused before they are parsed."""

    def test_oversized_input_is_413(self, client, minimal_df, monkeypatch):
        monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
        )
        assert response.status_code == 413

    def test_oversized_statement_is_413(self, client, make_statement_workbook, monkeypatch):
        monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
        response = client.post(
            "/statement-report",
            files={"statement_files": ("s.xlsx", make_statement_workbook().getvalue())},
        )
        assert response.status_code == 413

    def test_upload_at_the_limit_is_accepted(self, client, minimal_df, monkeypatch):
        content = _csv_bytes(minimal_df)
        monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", len(content))
        response = client.post(
            "/validate", files={"file": ("input.csv", content, "text/csv")}
        )
        assert response.status_code == 200


class TestValidate:
    """POST /validate."""

    def test_valid_file(self, client, minimal_df):
        """A valid Process Maker CSV returns a clean report."""
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
        )
        assert response.status_code == 200
        report = response.json()
        assert report["total_rows"] == 2
        assert report["valid_rows"] == 2
        assert report["errors"] == []
        assert report["warnings"] == []

    def test_file_with_errors(self, client, minimal_df):
        """Rows failing hard rules are reported, not silently dropped."""
        bad = minimal_df.copy()
        bad.loc[0, "airtime_phone"] = "123"  # not 9 digits after stripping
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(bad), "text/csv")},
        )
        assert response.status_code == 200
        report = response.json()
        assert report["valid_rows"] == 1
        assert len(report["errors"]) == 1
        assert report["errors"][0]["field"] == "airtime_phone"

    def test_unsupported_format_rejected(self, client):
        """A non-CSV/Excel upload is rejected with 400."""
        response = client.post(
            "/validate",
            files={"file": ("input.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400

    def test_unparseable_file_rejected(self, client):
        """A file pandas cannot parse is the client's problem: 400, not 500."""
        response = client.post(
            "/validate",
            files={"file": ("input.csv", b"", "text/csv")},
        )
        assert response.status_code == 400


class TestTransform:
    """POST /transform."""

    def test_valid_file_returns_xlsx(self, client, minimal_df, template_path):
        """A valid upload streams back a .xlsx with the expected filename."""
        response = client.post(
            "/transform",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == XLSX_MEDIA_TYPE
        assert response.headers["content-disposition"] == (
            'attachment; filename="input_openfloat.xlsx"'
        )
        assert len(response.content) > 0

    def test_all_rows_filtered_returns_422(self, client, minimal_df):
        """When every row fails validation, no output is produced → 422."""
        all_bad_phones = minimal_df.copy()
        all_bad_phones["airtime_phone"] = "123"
        response = client.post(
            "/transform",
            files={"file": ("input.csv", _csv_bytes(all_bad_phones), "text/csv")},
        )
        assert response.status_code == 422


class TestIdentifierColumnOverTheApi:
    """The identifier column is detected per request, or named explicitly."""

    def test_detects_staff_id_export(self, client, minimal_df):
        """A 'Staff ID' export transforms without any override."""
        staff_df = minimal_df.rename(columns={"unique_id": "Staff ID"})
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(staff_df), "text/csv")},
        )
        assert response.status_code == 200
        id_warnings = [w for w in response.json()["warnings"] if w["field"] == "account_name"]
        assert id_warnings == []

    def test_explicit_column_is_honored(self, client, minimal_df):
        """account_name_column names a column detection would not have picked."""
        no_id_df = minimal_df.rename(columns={"unique_id": "label"})
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(no_id_df), "text/csv")},
            data={"account_name_column": "label"},
        )
        assert response.status_code == 200
        id_warnings = [w for w in response.json()["warnings"] if w["field"] == "account_name"]
        assert id_warnings == []

    def test_stale_override_still_transforms(self, client, minimal_df):
        """A column missing from the file falls back to detection, never a 500."""
        response = client.post(
            "/transform",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"account_name_column": "Staff ID"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == XLSX_MEDIA_TYPE


class TestProjectCodeOverTheApi:
    """project_code completes a short case reference through the API too."""

    def test_project_code_form_field_composes(self, client, minimal_df):
        minimal_df["case_remark"] = ["C# 38305", "C#38305"]
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"project_code": "22505AA"},
        )
        assert response.status_code == 200
        assert [w for w in response.json()["warnings"] if w["field"] == "project_code"] == []

    def test_missing_project_code_reports_once(self, client, minimal_df):
        minimal_df["case_remark"] = ["C# 38305", "C#38305"]
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
        )
        assert response.status_code == 200
        code_warnings = [w for w in response.json()["warnings"] if w["field"] == "project_code"]
        assert len(code_warnings) == 1


class TestStatementReport:
    """POST /statement-report."""

    def test_single_statement(self, client, make_statement_workbook):
        """One statement file parses into a JSON StatementReport."""
        buffer = make_statement_workbook(
            rows=[
                {
                    "Transaction Status": "Successful",
                    "Account Number": 254712345678,
                    "Remark": "C#37154 13054AF RESP AIRTIME-KSH100 d05",
                    "Amount": 100,
                }
            ],
            footer_total=100,
        )
        response = client.post(
            "/statement-report",
            files=[
                ("statement_files", ("statement.xlsx", buffer.getvalue(), XLSX_MEDIA_TYPE)),
            ],
        )
        assert response.status_code == 200
        report = response.json()
        assert report["errors"] == []
        assert report["combined"]["total_rows"] == 1
        assert report["combined"]["successful_count"] == 1
        # Footer totals are per-file (footers don't combine across files).
        assert report["file_summaries"][0]["footer_matches"] is True
        assert report["reconciliation"] is None

    def test_multiple_statements_with_reconciliation(
        self, client, make_statement_workbook, pm_input_df
    ):
        """Multiple statements plus a Process Maker input reconcile per bucket."""
        paid = make_statement_workbook(
            rows=[
                {
                    "Transaction Status": "Successful",
                    "Account Number": 254712345678,
                    "Remark": "C#37154 13054AF RESP AIRTIME-KSH100 d05",
                    "Amount": 100,
                }
            ]
        )
        reversed_only = make_statement_workbook(
            rows=[
                {
                    "Transaction Status": "Reversed",
                    "Account Number": 254722345678,
                    "Remark": "C#37181 19340AK RESP AIRTIME-KSH100 d05",
                    "Amount": None,
                }
            ],
            include_reference_id=False,
        )
        response = client.post(
            "/statement-report",
            files=[
                ("statement_files", ("paid.xlsx", paid.getvalue(), XLSX_MEDIA_TYPE)),
                ("statement_files", ("reversed.xlsx", reversed_only.getvalue(), XLSX_MEDIA_TYPE)),
                ("input_file", ("input.csv", _csv_bytes(pm_input_df), "text/csv")),
            ],
        )
        assert response.status_code == 200
        report = response.json()
        assert report["errors"] == []
        assert report["combined"]["total_rows"] == 2
        assert report["combined"]["unsuccessful_count"] == 1
        # remark_parts serializes as a positional NamedTuple array
        txn = report["transactions"][0]
        assert txn["remark_parts"] == ["37154", "13054AF", "100", "d05"]

        rec = report["reconciliation"]
        assert [entry["phone"] for entry in rec["matched_paid"]] == ["254712345678"]
        assert [entry["phone"] for entry in rec["matched_not_paid"]] == ["254722345678"]
        missing = {entry["phone"] for entry in rec["missing_from_statement"]}
        assert "254733345678" in missing  # in input, never in either statement

    def test_malformed_file_lands_in_errors_not_500(self, client, make_statement_workbook):
        """A corrupt statement yields an error entry; the request still succeeds."""
        good = make_statement_workbook(
            rows=[
                {
                    "Transaction Status": "Successful",
                    "Account Number": 254712345678,
                    "Remark": "C#37154 13054AF RESP AIRTIME-KSH100 d05",
                    "Amount": 100,
                }
            ]
        )
        response = client.post(
            "/statement-report",
            files=[
                ("statement_files", ("good.xlsx", good.getvalue(), XLSX_MEDIA_TYPE)),
                ("statement_files", ("corrupt.xlsx", b"not an excel file", XLSX_MEDIA_TYPE)),
            ],
        )
        assert response.status_code == 200
        report = response.json()
        assert len(report["errors"]) == 1
        assert "corrupt.xlsx" in report["errors"][0]
        # The good file still reports.
        assert report["combined"]["total_rows"] == 1


def _paid_statement(make_statement_workbook) -> bytes:
    return make_statement_workbook(
        rows=[
            {
                "Transaction Status": "Successful",
                "Account Number": 254712345678,
                "Remark": "C#37154 13054AF RESP AIRTIME-KSH100 d05",
                "Amount": 100,
            }
        ]
    ).getvalue()


class TestBrowserProtection:
    """Only the app's own page, on localhost, can post to the API."""

    def test_post_without_client_header_is_403(self, minimal_df):
        bare = TestClient(app, base_url=LOCAL_BASE_URL)
        response = bare.post(
            "/validate", files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")}
        )
        assert response.status_code == 403

    def test_wrong_client_header_value_is_403(self, client, minimal_df):
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            headers={main.CLIENT_HEADER: "yes"},
        )
        assert response.status_code == 403

    def test_foreign_host_is_400(self):
        """A DNS-rebinding page still sends its own Host, and is refused."""
        foreign = TestClient(app, base_url="http://evil.example", headers=CLIENT_HEADERS)
        assert foreign.get("/health").status_code == 400

    def test_localhost_with_port_is_allowed(self):
        local = TestClient(app, base_url="http://localhost:8000")
        assert local.get("/health").status_code == 200

    def test_get_needs_no_header(self):
        """The page loads its defaults before anything is posted."""
        bare = TestClient(app, base_url=LOCAL_BASE_URL)
        assert bare.get("/settings").status_code == 200


class TestSettings:
    """GET /settings."""

    def test_returns_env_defaults(self, client, monkeypatch):
        monkeypatch.setattr(
            main,
            "settings",
            main.settings.model_copy(
                update={"max_amount_threshold": 5000, "project_code": "22505AA"}
            ),
        )
        body = client.get("/settings").json()
        assert body["max_amount_threshold"] == 5000
        assert body["project_code"] == "22505AA"
        assert body["default_country_prefix"] == "254"
        assert body["version"]


class TestRequestSettings:
    """Per-request settings override .env only where the request names them."""

    def test_omitted_project_code_means_none(self, client, case_df, monkeypatch):
        """The page sends what its box holds; .env reaches it through GET /settings."""
        monkeypatch.setattr(
            main, "settings", main.settings.model_copy(update={"project_code": "22505AA"})
        )
        response = client.post(
            "/validate", files={"file": ("input.csv", _csv_bytes(case_df), "text/csv")}
        )
        code_warnings = [w for w in response.json()["warnings"] if w["field"] == "project_code"]
        assert len(code_warnings) == 1

    def test_omitted_threshold_keeps_env_value(self, client, minimal_df, monkeypatch):
        monkeypatch.setattr(
            main, "settings", main.settings.model_copy(update={"max_amount_threshold": 100})
        )
        response = client.post(
            "/validate", files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")}
        )
        assert [w["field"] for w in response.json()["warnings"]] == ["amount", "amount"]

    @pytest.mark.parametrize("prefix", ["+254", " ", "2544", "ab"])
    def test_bad_country_prefix_is_422(self, client, minimal_df, prefix):
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"country_prefix": prefix},
        )
        assert response.status_code == 422

    def test_amount_threshold_is_applied(self, client, minimal_df):
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"max_amount_threshold": "100"},
        )
        assert [w["field"] for w in response.json()["warnings"]] == ["amount", "amount"]

    def test_negative_threshold_is_422(self, client, minimal_df):
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"max_amount_threshold": "-1"},
        )
        assert response.status_code == 422


class TestColumnOverrides:
    """column_overrides points a field at a column detection would not find."""

    def test_override_rescues_unrecognised_header(self, client, minimal_df):
        odd = minimal_df.rename(columns={"amount": "Payout"})
        files = {"file": ("input.csv", _csv_bytes(odd), "text/csv")}
        assert client.post("/validate", files=files).json()["valid_rows"] == 0

        response = client.post(
            "/validate", files=files, data={"column_overrides": '{"amount": "Payout"}'}
        )
        assert response.json()["valid_rows"] == 2

    @pytest.mark.parametrize(
        "raw", ["not json", "[1, 2]", '{"amount": 5}', '{"made_up_field": "KES"}']
    )
    def test_malformed_overrides_are_422(self, client, minimal_df, raw):
        response = client.post(
            "/validate",
            files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")},
            data={"column_overrides": raw},
        )
        assert response.status_code == 422


class TestPreview:
    """POST /preview: the whole Transform page in one response."""

    def test_clean_file(self, client, minimal_df):
        response = client.post(
            "/preview", files={"file": ("input.csv", _csv_bytes(minimal_df), "text/csv")}
        )
        assert response.status_code == 200
        body = response.json()
        preview = body["preview"]
        assert preview["row_count"] == 2
        assert preview["missing_fields"] == []
        assert preview["identifier_column"] == "unique_id"
        assert preview["identifier_samples"] == ["TEST001", "TEST002"]
        assert len(preview["preview_rows"]) == 2
        assert body["report"]["valid_rows"] == 2
        assert body["output_row_count"] == 2

    def test_missing_field_and_override(self, client, minimal_df):
        odd = minimal_df.rename(columns={"amount": "Payout"})
        files = {"file": ("input.csv", _csv_bytes(odd), "text/csv")}

        before = client.post("/preview", files=files).json()
        assert before["preview"]["missing_fields"] == ["amount"]
        assert before["output_row_count"] == 0

        after = client.post(
            "/preview", files=files, data={"column_overrides": '{"amount": "Payout"}'}
        ).json()
        assert after["preview"]["missing_fields"] == []
        assert after["preview"]["mapping"]["amount"] == "Payout"
        assert after["output_row_count"] == 2

    def test_composed_remark_preview(self, client, case_df):
        response = client.post(
            "/preview",
            files={"file": ("input.csv", _csv_bytes(case_df), "text/csv")},
            data={"project_code": "22505AA"},
        )
        preview = response.json()["preview"]
        assert preview["short_form_rows"] == 2
        assert preview["remark_preview"] == "C#38305 22505AA RESP AIRTIME-KSH350 g05"
        assert preview["remark_readable"] is True


class TestRejectedRows:
    """POST /rejected-rows."""

    def test_returns_rows_to_fix(self, client, minimal_df):
        bad = minimal_df.copy()
        bad.loc[0, "airtime_phone"] = "123"
        response = client.post(
            "/rejected-rows", files={"file": ("input.csv", _csv_bytes(bad), "text/csv")}
        )
        assert response.status_code == 200
        assert response.headers["content-disposition"] == (
            'attachment; filename="input_rows_to_fix.xlsx"'
        )
        sheet = pd.read_excel(io.BytesIO(response.content))
        assert len(sheet) == 1
        assert "unique_id" in sheet.columns  # the file's own headers


class TestStatementWorkbook:
    """POST /statement-report/workbook."""

    @pytest.mark.parametrize(
        ("kind", "filename"),
        [
            ("report", "C#37154 13054AF RESP AIRTIME-KSH100 d05_report.xlsx"),
            ("finance", "C#37154 13054AF RESP AIRTIME-KSH100 d05.xlsx"),
        ],
    )
    def test_named_after_the_remark(self, client, make_statement_workbook, kind, filename):
        response = client.post(
            "/statement-report/workbook",
            params={"kind": kind},
            files=[
                (
                    "statement_files",
                    ("s.xlsx", _paid_statement(make_statement_workbook), XLSX_MEDIA_TYPE),
                )
            ],
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == XLSX_MEDIA_TYPE
        assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'

    def test_non_ascii_name_is_encoded(self, client, make_statement_workbook):
        statement = make_statement_workbook(
            rows=[{"Transaction Status": "Successful", "Remark": "Malipo é", "Amount": 1}]
        ).getvalue()
        response = client.post(
            "/statement-report/workbook",
            params={"kind": "finance"},
            files=[("statement_files", ("s.xlsx", statement, XLSX_MEDIA_TYPE))],
        )
        assert response.headers["content-disposition"] == (
            "attachment; filename*=UTF-8''" + quote("Malipo é.xlsx")
        )

    def test_unknown_kind_is_422(self, client, make_statement_workbook):
        response = client.post(
            "/statement-report/workbook",
            params={"kind": "everything"},
            files=[("statement_files", ("s.xlsx", _paid_statement(make_statement_workbook)))],
        )
        assert response.status_code == 422


class TestShutdown:
    """POST /shutdown replies, then stops the server."""

    def test_replies_then_signals(self, client, monkeypatch):
        # The real signal would stop pytest itself; record it instead.
        raised = threading.Event()
        monkeypatch.setattr(main, "SHUTDOWN_DELAY_SECONDS", 0)
        monkeypatch.setattr(signal, "raise_signal", lambda signum: raised.set())

        response = client.post("/shutdown")

        assert response.status_code == 200
        assert raised.wait(timeout=5)

    def test_uses_the_launchers_hook_when_registered(self, client, monkeypatch):
        """serve.py's hook stops uvicorn with exit code 0; no signal is raised."""
        stopped = threading.Event()
        monkeypatch.setattr(main, "SHUTDOWN_DELAY_SECONDS", 0)
        monkeypatch.setattr(app.state, "shutdown", stopped.set, raising=False)
        monkeypatch.setattr(
            signal, "raise_signal", lambda signum: pytest.fail("signal raised")
        )

        client.post("/shutdown")

        assert stopped.wait(timeout=5)

    def test_needs_client_header(self):
        bare = TestClient(app, base_url=LOCAL_BASE_URL)
        assert bare.post("/shutdown").status_code == 403
