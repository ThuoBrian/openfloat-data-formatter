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
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import pandas as pd

from .config import settings
from .models import StatementReport, ValidationReport
from .statement import build_statement_report
from .transformer import transform
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/validate", response_model=ValidationReport)
async def validate_file(file: UploadFile = File(...)):
    """Validate a Process Maker CSV/Excel file without transforming it.

    Returns a JSON validation report with row counts, errors, and warnings.
    """
    df = await _read_uploaded_file(file)
    report = run_validation(df)
    return report


@app.post("/transform")
async def transform_file(file: UploadFile = File(...)):
    """Transform a Process Maker CSV/Excel file into an OpenFloat-ready Excel file.

    Returns the transformed .xlsx file as a binary download.
    """
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename).suffix
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = transform(tmp_path)
    finally:
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

    if result.output is None:
        raise HTTPException(
            status_code=422,
            detail="Transformation produced no output. Check validation report for errors.",
        )

    # Stream the output buffer
    result.output.seek(0)
    filename = Path(file.filename).stem + "_openfloat.xlsx"

    return StreamingResponse(
        result.output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/statement-report", response_model=StatementReport)
async def statement_report(
    statement_files: list[UploadFile] = File(...),
    input_file: UploadFile | None = File(None),
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
        source_names=[statement_file.filename for statement_file in statement_files],
        input_df=input_df,
        config=settings,
    )
    return report


async def _read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded file into a pandas DataFrame.

    Supports CSV and Excel (.xlsx, .xls, .xlsm) formats.
    """
    suffix = Path(file.filename).suffix.lower()
    content = await file.read()

    if suffix == ".csv":
        return pd.read_csv(io.BytesIO(content))
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        return pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: '{suffix}'. "
            f"Expected .csv, .xlsx, .xls, or .xlsm.",
        )