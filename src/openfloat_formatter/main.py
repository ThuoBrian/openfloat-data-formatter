"""FastAPI application for the OpenFloat Data Formatter.

Provides REST endpoints for file upload, validation, transformation, and
statement reporting.

Endpoints:
    POST /transform         - Upload CSV/Excel, download OpenFloat-ready .xlsx
    POST /validate          - Upload CSV/Excel, get JSON validation report
    POST /statement-report  - Upload OpenFloat Transaction Statement export(s),
                              get a JSON report on successful vs unsuccessful
                              transactions (optionally reconciled against a
                              Process Maker input)
    GET  /health            - Health check
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import Settings, settings
from .models import StatementReport, ValidationReport
from .normalizer import canonicalize_input_columns
from .statement import build_statement_report
from .transformer import transform_frame
from .validator import validate as run_validation

app = FastAPI(
    title="OpenFloat Data Formatter",
    description="Transform Process Maker airtime exports into OpenFloat-ready uploads.",
    version="0.1.0",
)

# CORS for browser-based API clients. The bundled Streamlit UI does not call
# this API (it imports the pipeline modules directly); the API exists for
# external/scripted consumers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _request_config(
    account_name_column: str | None = None,
    project_code: str | None = None,
) -> Settings:
    """Per-request settings, overriding only what the request named.

    Copies the singleton rather than building a fresh `Settings()`, which would
    re-read .env on every request and could raise at request time.
    """
    return settings.model_copy(
        update={
            "account_name_column": account_name_column,
            "project_code": project_code,
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/validate", response_model=ValidationReport)
async def validate_file(
    file: Annotated[UploadFile, File()],
    account_name_column: Annotated[str | None, Form()] = None,
    project_code: Annotated[str | None, Form()] = None,
):
    """Validate a Process Maker CSV/Excel file without transforming it.

    Returns a JSON validation report with row counts, errors, and warnings.
    `account_name_column` optionally names the identifier column feeding the
    output 'Account Name'; omit it to detect the column from the headers.
    `project_code` completes a short `C#<case>` reference into the full Remark.
    """
    df = await _read_uploaded_file(file)
    report = run_validation(df, _request_config(account_name_column, project_code))
    return report


@app.post("/transform")
async def transform_file(
    file: Annotated[UploadFile, File()],
    account_name_column: Annotated[str | None, Form()] = None,
    project_code: Annotated[str | None, Form()] = None,
):
    """Transform a Process Maker CSV/Excel file into an OpenFloat-ready Excel file.

    Returns the transformed .xlsx file as a binary download.
    `account_name_column` optionally names the identifier column feeding the
    output 'Account Name'; omit it to detect the column from the headers.
    `project_code` completes a short `C#<case>` reference into the full Remark.
    """
    # Read straight into a frame: an upload can carry names, phone numbers and
    # staff IDs, and a temp file would put them on disk for the duration.
    frame = await _read_uploaded_file(file)
    result = transform_frame(
        frame, _request_config(account_name_column, project_code)
    )

    if result.output is None:
        raise HTTPException(
            status_code=422,
            detail="Transformation produced no output. Check validation report for errors.",
        )

    # Stream the output buffer
    result.output.seek(0)
    filename = Path(file.filename or "upload").stem + "_openfloat.xlsx"

    return StreamingResponse(
        result.output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/statement-report", response_model=StatementReport)
async def statement_report(
    statement_files: Annotated[list[UploadFile], File()],
    input_file: Annotated[UploadFile | None, File()] = None,
):
    """Report on successful vs unsuccessful OpenFloat disbursements.

    Accepts one or more 'Transaction Statement' exports plus an optional
    Process Maker input (enables reconciliation). Statement files are parsed
    in memory; a statement with structural problems lands in `errors` and
    does not fail the request — only a request where nothing parses is
    useless, and even then the response is a valid (empty) report.

    JSON shape note: `remark_parts` serializes as a positional array
    (`[case_number, project_code, amount, activity_code]`) because
    `CaseRemarkParts` is a NamedTuple.
    """
    input_df = await _read_uploaded_file(input_file) if input_file else None
    report = build_statement_report(
        [io.BytesIO(await statement_file.read()) for statement_file in statement_files],
        source_names=[statement_file.filename or "unnamed" for statement_file in statement_files],
        input_df=input_df,
        config=settings,
    )
    return report


async def _read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded file into a pandas DataFrame.

    Supports CSV and Excel (.xlsx, .xls, .xlsm) formats.
    """
    suffix = Path(file.filename or "").suffix.lower()
    content = await file.read()

    if suffix == ".csv":
        return canonicalize_input_columns(pd.read_csv(io.BytesIO(content)))
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        return canonicalize_input_columns(pd.read_excel(io.BytesIO(content)))
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: '{suffix}'. "
            f"Expected .csv, .xlsx, .xls, or .xlsm.",
        )
