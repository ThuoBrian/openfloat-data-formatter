"""FastAPI application for the OpenFloat Data Formatter.

Provides REST endpoints for file upload, validation, and transformation.

Endpoints:
    POST /transform  - Upload CSV/Excel, download OpenFloat-ready .xlsx
    POST /validate   - Upload CSV/Excel, get JSON validation report
    GET  /health     - Health check
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .models import ValidationReport
from .transformer import transform
from .validator import validate as run_validation

import pandas as pd

app = FastAPI(
    title="OpenFloat Data Formatter",
    description="Transform Process Maker airtime exports into OpenFloat-ready uploads.",
    version="0.1.0",
)

# CORS middleware for Streamlit frontend
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


async def _read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded file into a pandas DataFrame.

    Supports CSV and Excel (.xlsx, .xls, .xlsm) formats.
    """
    suffix = Path(file.filename).suffix.lower()
    content = await file.read()

    if suffix == ".csv":
        import io

        return pd.read_csv(io.BytesIO(content))
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        import io

        return pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: '{suffix}'. "
            f"Expected .csv, .xlsx, .xls, or .xlsm.",
        )