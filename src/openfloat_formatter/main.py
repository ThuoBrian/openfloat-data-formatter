"""FastAPI application for the OpenFloat Data Formatter.

Provides REST endpoints for file upload, validation, transformation, and
statement reporting. It only ever runs on 127.0.0.1: everything here works
offline, and the files it takes carry names, phone numbers and staff IDs.

Endpoints:
    GET  /health                       - Health check
    GET  /settings                     - The defaults the app's controls start from
    POST /preview                      - Upload CSV/Excel, get the column mapping,
                                         validation report and output row count
    POST /validate                     - Upload CSV/Excel, get JSON validation report
    POST /transform                    - Upload CSV/Excel, download OpenFloat-ready .xlsx
    POST /rejected-rows                - Upload CSV/Excel, download the rows left out
    POST /statement-report             - Upload OpenFloat Transaction Statement export(s),
                                         get a JSON report on successful vs unsuccessful
                                         transactions (optionally reconciled against a
                                         Process Maker input)
    POST /statement-report/workbook    - The same inputs, download the project leads'
                                         report (kind=report) or finance sheet (kind=finance)
    POST /shutdown                     - Stop the app

Every POST requires the `X-OpenFloat-Client: 1` header (see `_require_client`).
"""

from __future__ import annotations

import io
import signal
import threading
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError

from . import app_version
from .config import COUNTRY_PREFIX_PATTERN, INPUT_COLUMN_ALIASES, Settings
from .models import StatementReport, UiDefaults, UploadCheck, ValidationReport
from .normalizer import canonicalize_input_columns
from .statement import build_statement_report
from .transformer import read_input_file, transform_frame
from .upload_preview import describe_upload
from .validator import validate as run_validation
from .writer import (
    StatementWorkbook,
    statement_download_name,
    write_finance_workbook,
    write_rejected_rows_workbook,
    write_statement_workbook,
)

# Read once at startup: a bad .env stops the API here, before it serves
# anything, rather than failing on the first request.
settings = Settings()

app = FastAPI(
    title="OpenFloat Data Formatter",
    description="Transform Process Maker airtime exports into OpenFloat-ready uploads.",
    version="0.1.0",
)

# Browser protection for a server on localhost with no login. The API is bound
# to 127.0.0.1, but any web page open in the same browser can still aim
# requests at it, and these uploads carry personal data.
#
# - No CORS middleware, on purpose: without it no other origin can read a
#   response, and a wildcard origin would let any page read them.
# - Host check: a DNS-rebinding page resolves its own name to 127.0.0.1 to
#   become same-origin; its requests still carry its own Host, so they stop here.
# - Custom header on every POST (`_require_client`): a multipart form post is
#   a "simple" request a cross-site page can send blind, but one with a custom
#   header needs a CORS preflight first, which fails because there is no CORS.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

CLIENT_HEADER = "X-OpenFloat-Client"

# Real exports are a few hundred KB; this only stops a runaway upload from
# being parsed into memory.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Time for the /shutdown response to reach the browser before the server goes.
SHUTDOWN_DELAY_SECONDS = 0.5

_OVERRIDES_ADAPTER = TypeAdapter(dict[str, str])


async def _require_client(
    x_openfloat_client: Annotated[str | None, Header()] = None,
) -> None:
    """Refuse a POST that lacks the app's own header (see the block above)."""
    if x_openfloat_client != "1":
        raise HTTPException(
            status_code=403, detail=f"Missing the '{CLIENT_HEADER}: 1' header."
        )


CLIENT_ONLY = [Depends(_require_client)]


# Form fields shared by every endpoint that reads a Process Maker file.
#
# The identifier column and project code are per-upload choices that can be
# "none", so what the request sends is the value and leaving one out means
# none (detect the identifier; no project code). The app's page starts those
# controls from GET /settings, which is how .env reaches it. FastAPI reads an
# empty form field as not sent, so "" could not mean anything else anyway.
# The country prefix and threshold can't be "none": left out, they keep .env.
AccountNameColumn = Annotated[
    str | None,
    Form(description="Column feeding 'Account Name'. Omit to detect it from the headers."),
]
ProjectCode = Annotated[
    str | None,
    Form(description="Completes a short 'C#<case>' reference into the full Remark."),
]
ColumnOverrides = Annotated[
    str | None,
    Form(description='JSON object, canonical field → column, e.g. {"amount": "Amount KES"}.'),
]
CountryPrefix = Annotated[
    str | None, Form(description="1-3 digits. Omit for the .env value.")
]
AmountThreshold = Annotated[
    int | None, Form(ge=0, description="Warn above this many KES. Omit for .env.")
]


def _base_config(
    country_prefix: str | None = None, max_amount_threshold: int | None = None
) -> Settings:
    """The startup settings with this request's prefix and threshold, if it sent them.

    Copies the singleton rather than building a fresh `Settings()`, which would
    re-read .env on every request and could raise at request time.
    `model_copy` skips validation, so the country prefix is checked here: a
    blank or '+254' prefix would silently rewrite every number in the batch.
    """
    update: dict[str, Any] = {}
    if country_prefix is not None:
        prefix = country_prefix.strip()
        if not COUNTRY_PREFIX_PATTERN.fullmatch(prefix):
            raise HTTPException(
                status_code=422, detail="Country prefix must be 1 to 3 digits, e.g. 254."
            )
        update["default_country_prefix"] = prefix
    if max_amount_threshold is not None:
        update["max_amount_threshold"] = max_amount_threshold
    return settings.model_copy(update=update)


def _request_config(
    account_name_column: str | None = None,
    project_code: str | None = None,
    country_prefix: str | None = None,
    max_amount_threshold: int | None = None,
) -> Settings:
    """Settings for one upload: see the block above for what an omitted field means."""
    return _base_config(country_prefix, max_amount_threshold).model_copy(
        update={
            "account_name_column": (account_name_column or "").strip() or None,
            "project_code": (project_code or "").strip() or None,
        }
    )


def _parse_overrides(raw: str | None) -> dict[str, str]:
    """The `column_overrides` form field, checked before it renames anything.

    Only canonical fields are accepted: an unknown key would be taken as a
    canonical name and rename the user's column to it, losing that column.
    """
    if not raw:
        return {}
    try:
        overrides = _OVERRIDES_ADAPTER.validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="column_overrides must be a JSON object of field name to column name.",
        ) from exc
    unknown = sorted(set(overrides) - set(INPUT_COLUMN_ALIASES))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown field(s) in column_overrides: {', '.join(unknown)}.",
        )
    return overrides


def _xlsx_response(buffer: io.BytesIO, filename: str) -> StreamingResponse:
    """Stream a workbook as a download named `filename`.

    The name can come from a Remark or an uploaded file's name, so anything
    beyond plain ASCII goes in the RFC 5987 `filename*` form rather than
    being pasted raw into the header.
    """
    buffer.seek(0)
    if filename.isascii() and '"' not in filename and "\\" not in filename:
        disposition = f'attachment; filename="{filename}"'
    else:
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/settings", response_model=UiDefaults)
async def ui_defaults() -> UiDefaults:
    """The values the app's controls start from: built-in defaults plus .env."""
    return UiDefaults(
        default_country_prefix=settings.default_country_prefix,
        max_amount_threshold=settings.max_amount_threshold,
        project_code=settings.project_code,
        account_name_column=settings.account_name_column,
        version=app_version(),
    )


@app.post("/preview", response_model=UploadCheck, dependencies=CLIENT_ONLY)
async def preview_file(
    file: Annotated[UploadFile, File()],
    account_name_column: AccountNameColumn = None,
    project_code: ProjectCode = None,
    column_overrides: ColumnOverrides = None,
    country_prefix: CountryPrefix = None,
    max_amount_threshold: AmountThreshold = None,
) -> UploadCheck:
    """Everything the Transform page shows for one file and one set of choices.

    Stateless on purpose: the app posts the file again whenever a choice
    changes, so nothing from an upload outlives its request.
    """
    config = _request_config(
        account_name_column, project_code, country_prefix, max_amount_threshold
    )
    overrides = _parse_overrides(column_overrides)
    raw_df = await _read_raw_upload(file)
    result = transform_frame(canonicalize_input_columns(raw_df, overrides), config)
    return UploadCheck(
        preview=describe_upload(raw_df, config, overrides),
        report=result.validation_report,
        output_row_count=result.output_row_count,
    )


@app.post("/validate", response_model=ValidationReport, dependencies=CLIENT_ONLY)
async def validate_file(
    file: Annotated[UploadFile, File()],
    account_name_column: AccountNameColumn = None,
    project_code: ProjectCode = None,
    column_overrides: ColumnOverrides = None,
    country_prefix: CountryPrefix = None,
    max_amount_threshold: AmountThreshold = None,
):
    """Validate a Process Maker CSV/Excel file without transforming it.

    Returns a JSON validation report with row counts, errors, and warnings.
    """
    config = _request_config(
        account_name_column, project_code, country_prefix, max_amount_threshold
    )
    df = await _read_uploaded_file(file, _parse_overrides(column_overrides))
    return run_validation(df, config)


@app.post("/transform", dependencies=CLIENT_ONLY)
async def transform_file(
    file: Annotated[UploadFile, File()],
    account_name_column: AccountNameColumn = None,
    project_code: ProjectCode = None,
    column_overrides: ColumnOverrides = None,
    country_prefix: CountryPrefix = None,
    max_amount_threshold: AmountThreshold = None,
):
    """Transform a Process Maker CSV/Excel file into an OpenFloat-ready Excel file.

    Returns the transformed .xlsx file as a binary download.
    """
    config = _request_config(
        account_name_column, project_code, country_prefix, max_amount_threshold
    )
    # Read straight into a frame: an upload can carry names, phone numbers and
    # staff IDs, and a temp file would put them on disk for the duration.
    frame = await _read_uploaded_file(file, _parse_overrides(column_overrides))
    result = transform_frame(frame, config)

    if result.output is None:
        raise HTTPException(
            status_code=422,
            detail="Transformation produced no output. Check validation report for errors.",
        )
    return _xlsx_response(result.output, Path(file.filename or "upload").stem + "_openfloat.xlsx")


@app.post("/rejected-rows", dependencies=CLIENT_ONLY)
async def rejected_rows(
    file: Annotated[UploadFile, File()],
    account_name_column: AccountNameColumn = None,
    project_code: ProjectCode = None,
    column_overrides: ColumnOverrides = None,
    country_prefix: CountryPrefix = None,
    max_amount_threshold: AmountThreshold = None,
):
    """The rows that will be left out, in the file's own columns, with the reason.

    This is what goes back to whoever compiled the export, so it carries their
    headers rather than the canonical ones.
    """
    config = _request_config(
        account_name_column, project_code, country_prefix, max_amount_threshold
    )
    raw_df = await _read_raw_upload(file)
    report = run_validation(
        canonicalize_input_columns(raw_df, _parse_overrides(column_overrides)), config
    )
    return _xlsx_response(
        write_rejected_rows_workbook(raw_df, report),
        Path(file.filename or "upload").stem + "_rows_to_fix.xlsx",
    )


async def _statement_report(
    statement_files: list[UploadFile],
    input_file: UploadFile | None,
    country_prefix: str | None,
) -> StatementReport:
    """Build the report both statement endpoints return, one way."""
    config = _base_config(country_prefix)
    input_df = await _read_uploaded_file(input_file) if input_file else None
    return build_statement_report(
        [io.BytesIO(await _read_upload_bytes(upload)) for upload in statement_files],
        source_names=[upload.filename or "unnamed" for upload in statement_files],
        input_df=input_df,
        config=config,
    )


@app.post("/statement-report", response_model=StatementReport, dependencies=CLIENT_ONLY)
async def statement_report(
    statement_files: Annotated[list[UploadFile], File()],
    input_file: Annotated[UploadFile | None, File()] = None,
    country_prefix: CountryPrefix = None,
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
    return await _statement_report(statement_files, input_file, country_prefix)


@app.post("/statement-report/workbook", dependencies=CLIENT_ONLY)
async def statement_workbook(
    statement_files: Annotated[list[UploadFile], File()],
    kind: Annotated[StatementWorkbook, Query()],
    input_file: Annotated[UploadFile | None, File()] = None,
    country_prefix: CountryPrefix = None,
):
    """Download the project leads' report (`kind=report`) or the finance sheet."""
    report = await _statement_report(statement_files, input_file, country_prefix)
    writer = write_statement_workbook if kind == "report" else write_finance_workbook
    name = statement_download_name(
        report, [upload.filename or "unnamed" for upload in statement_files], kind
    )
    return _xlsx_response(writer(report), name)


def _shut_down() -> None:
    """Stop the server cleanly.

    `serve.py`, which is what run.bat launches, registers `app.state.shutdown`:
    it asks uvicorn to stop and return normally, so the process exits 0 and
    run.bat ends without its error pause.

    Raising SIGTERM is only the fallback for a bare `uvicorn` command (`just
    api`). uvicorn stops cleanly on it but then re-raises the signal, so the
    process exits non-zero (3 on Windows). That's fine for a developer but
    would leave run.bat's window paused on an error, hence the hook.
    """
    request_shutdown = getattr(app.state, "shutdown", None)
    if request_shutdown is not None:
        request_shutdown()
    else:
        signal.raise_signal(signal.SIGTERM)


@app.post("/shutdown", dependencies=CLIENT_ONLY)
async def shutdown() -> dict[str, str]:
    """Stop the app. Replies first, so the page can say it has closed."""
    threading.Timer(SHUTDOWN_DELAY_SECONDS, _shut_down).start()
    return {"status": "stopping"}


async def _read_raw_upload(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded file into a DataFrame with the file's own headers.

    Supports CSV and Excel (.xlsx, .xls, .xlsm) formats. An unsupported or
    unparseable file is the client's problem, so it is a 400, not a 500.
    """
    content = await _read_upload_bytes(file)
    try:
        return read_input_file(io.BytesIO(content), file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _read_uploaded_file(
    file: UploadFile, overrides: dict[str, str] | None = None
) -> pd.DataFrame:
    """Read an upload and rename its columns to the canonical names."""
    return canonicalize_input_columns(await _read_raw_upload(file), overrides)


async def _read_upload_bytes(file: UploadFile) -> bytes:
    """Read an upload, refusing one larger than MAX_UPLOAD_BYTES with a 413.

    Reads one byte past the limit rather than trusting a client-supplied size,
    so an oversized file is caught without being read in full.
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"'{file.filename}' is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    return content

