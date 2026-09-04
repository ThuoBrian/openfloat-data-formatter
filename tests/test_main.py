"""Tests for the FastAPI layer — endpoints in openfloat_formatter.main."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from openfloat_formatter.main import app

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


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
        all_no_consent = minimal_df.copy()
        all_no_consent["consent"] = "No"
        response = client.post(
            "/transform",
            files={"file": ("input.csv", _csv_bytes(all_no_consent), "text/csv")},
        )
        assert response.status_code == 422


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