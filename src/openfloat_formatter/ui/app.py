"""Streamlit UI for the OpenFloat Data Formatter.

Provides a simple web interface for non-technical staff to:
1. Transform: upload a Process Maker CSV/Excel file, preview and validate it,
   and download the transformed OpenFloat-ready Excel file
2. Statement Report: upload OpenFloat Transaction Statement exports and get a
   report on successful vs unsuccessful transactions, optionally reconciled
   against the original Process Maker input to find beneficiaries who were
   never paid
"""

from __future__ import annotations

import html
import re
import signal
import threading
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from openfloat_formatter.config import (
    COUNTRY_PREFIX_PATTERN,
    DEFAULT_TEMPLATE_PATH,
    Settings,
)
from openfloat_formatter.models import StatementReport, ValidationIssue, ValidationReport
from openfloat_formatter.normalizer import (
    canonicalize_input_columns,
    find_account_name_column,
    parse_case_remark,
    read_text_cell,
    resolve_input_columns,
)
from openfloat_formatter.remark import (
    build_remark,
    count_short_form_rows,
    find_project_code_column,
)
from openfloat_formatter.statement import build_statement_report
from openfloat_formatter.transformer import read_input_file, transform_frame
from openfloat_formatter.validator import remark_context
from openfloat_formatter.writer import (
    remark_file_stem,
    write_finance_workbook,
    write_rejected_rows_workbook,
    write_statement_workbook,
)


def main():
    st.set_page_config(
        page_title="OpenFloat Data Formatter",
        page_icon=str(_ICON_PATH),
        layout="wide",
    )
    st.html(_PAGE_CSS)
    _render_header()

    if st.session_state.get("closing"):
        st.success(
            "**The app has closed.** You can close this browser tab now. "
            "To use it again, open the **OpenFloat Data Formatter** shortcut."
        )
        st.caption(
            "If a \"Connection error\" message appears, that is expected — the "
            "app is no longer running."
        )
        # Delayed so this message reaches the browser before the server goes.
        threading.Timer(1.0, _shut_down).start()
        st.stop()

    # The mode choice is the first decision anyone makes, so it sits on the
    # page itself — a sidebar radio is easy to miss, and is hidden entirely
    # when the sidebar is collapsed or the window is narrow.
    mode = st.radio(
        "What do you want to do?",
        [MODE_TRANSFORM, MODE_STATEMENT],
        horizontal=True,
        captions=[
            "Turn a Process Maker export into a file OpenFloat accepts.",
            "After a disbursement: see who was paid and who wasn't.",
        ],
    )

    with st.sidebar:
        st.markdown("#### How it works")
        st.markdown(
            "1. **Prepare an upload** from your Process Maker export.\n"
            "2. Upload that file to OpenFloat yourself.\n"
            "3. When it finishes, download OpenFloat's **Transaction "
            "Statement** and come back to **Check payment results**."
        )
        # Uploaders keep their file across reruns; changing their key is the
        # only way to empty them, so "start over" bumps a counter in the key.
        if st.button(
            "Start over with new files", icon=":material/restart_alt:", width="stretch"
        ):
            st.session_state["upload_round"] = st.session_state.get("upload_round", 0) + 1
            st.rerun()
        st.divider()

    # Free text that silently corrupts every phone number in a batch if it is
    # mistyped, on a tool only used for Kenyan numbers — it belongs out of the
    # way, not beside the upload button.
    # One expander for both modes; the threshold only matters to Transform, so
    # it only shows there.
    with st.sidebar.expander("Advanced settings", icon=":material/tune:"):
        country_prefix = st.text_input(
            "Country prefix",
            value="254",
            help="Country code prepended to phone numbers",
        ).strip()
        amount_threshold = (
            st.number_input(
                "Max amount threshold (KES)",
                min_value=0,
                value=10_000,
                help="Warn when airtime amount exceeds this value",
            )
            if mode == MODE_TRANSFORM
            else 0
        )

    # Last in the sidebar and behind a confirmation: one stray click otherwise
    # throws away a file the user has prepared but not yet downloaded.
    st.sidebar.divider()
    if st.sidebar.button(
        "Close the app",
        icon=":material/power_settings_new:",
        help="Stops the tool and closes its black window.",
        width="stretch",
    ):
        _confirm_close()
    st.sidebar.caption(f"Version {_app_version()} · Runs on this computer only")

    # A blank or mistyped prefix would silently rewrite every phone number in
    # the batch, so nothing runs until it is a plain country code.
    if not COUNTRY_PREFIX_PATTERN.fullmatch(country_prefix):
        st.sidebar.error("Country prefix must be 1 to 3 digits, e.g. 254.")
        st.stop()

    if mode == MODE_TRANSFORM:
        render_transform_page(country_prefix, int(amount_threshold))
    else:
        render_statement_report_page(country_prefix)


MODE_TRANSFORM = "Prepare an OpenFloat upload"
MODE_STATEMENT = "Check payment results"

AUTO_DETECT = "(auto-detect)"

# Same artwork as the desktop shortcut (install/openfloat.ico); both come from
# scripts/generate_icon.py.
_ICON_PATH = Path(__file__).with_name("icon.png")

# Page accents; the rest of the palette is the theme in .streamlit/config.toml.
_HEADER_BG = "#1E293B"  # header band (slate 800), one step up from the page
_HEADER_BORDER = "#334155"  # slate 700, matches the theme's borderColor
_ACCENT = "#2563EB"  # step badges, matches the theme's primaryColor
_HEADING = "#F1F5F9"  # step titles (slate 100)
_MUTED = "#94A3B8"  # secondary text (slate 400), 7:1 on the page

# The theme covers colours and fonts; this covers what it can't — the header
# band, the step badges, and a readable line length on wide monitors. Selectors
# stick to Streamlit's `data-testid` attributes and our own classes, which are
# far more stable across releases than its generated class names.
_PAGE_CSS = f"""
<style>
  [data-testid="stMainBlockContainer"] {{
    max-width: 1240px;
    padding-top: 2.25rem;
  }}
  .of-header {{
    background: {_HEADER_BG};
    border: 1px solid {_HEADER_BORDER};
    border-radius: 10px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
    color: #FFFFFF;
    padding: 1.1rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
  }}
  .of-header h1 {{
    color: #FFFFFF;
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin: 0;
    padding: 0;
  }}
  .of-header p {{
    color: #CBD5E1;
    font-size: 0.9rem;
    margin: 0.2rem 0 0 0;
  }}
  .of-badge {{
    border: 1px solid rgba(255, 255, 255, 0.45);
    border-radius: 999px;
    font-size: 0.8rem;
    padding: 0.3rem 0.8rem;
    white-space: nowrap;
  }}
  .of-step {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 1.75rem 0 0.25rem 0;
  }}
  .of-step-number {{
    background: {_ACCENT};
    border-radius: 50%;
    color: #FFFFFF;
    flex: none;
    font-weight: 700;
    height: 2rem;
    line-height: 2rem;
    text-align: center;
    width: 2rem;
  }}
  .of-step-title {{
    color: {_HEADING};
    font-size: 1.3rem;
    letter-spacing: -0.01em;
    font-weight: 600;
  }}
  .of-step-optional {{
    color: {_MUTED};
    font-size: 0.85rem;
    font-weight: 400;
    margin-left: 0.25rem;
  }}
</style>
"""


def _app_version() -> str:
    try:
        return version("openfloat-data-formatter")
    except PackageNotFoundError:  # running from a checkout that isn't installed
        return "dev"


def _render_header() -> None:
    st.html(
        '<div class="of-header"><div>'
        "<h1>OpenFloat Data Formatter</h1>"
        "<p>Airtime disbursement files for OpenFloat, checked before you upload "
        "and reconciled after.</p>"
        '</div><span class="of-badge">&#128274; Files stay on this computer</span></div>'
    )


def _step(number: int, title: str, *, optional: bool = False) -> None:
    """A numbered step heading — the page's main way of saying "you are here"."""
    suffix = '<span class="of-step-optional">(optional)</span>' if optional else ""
    st.html(
        f'<div class="of-step"><span class="of-step-number">{number}</span>'
        f'<span class="of-step-title">{html.escape(title)}{suffix}</span></div>'
    )


def _shut_down() -> None:
    """Stop the Streamlit server the way Ctrl+C in its window would.

    Streamlit handles SIGTERM itself — it stops the server and the process
    exits with code 0 — so `run.bat` reaches its end without hitting the
    "exited with an error" pause, and the black window closes on its own.
    `os._exit` or killing the process would skip that clean shutdown and,
    on Windows, exit non-zero, leaving the window paused on an error.
    """
    signal.raise_signal(signal.SIGTERM)


@st.dialog("Close the app?")
def _confirm_close() -> None:
    st.write(
        "This stops the OpenFloat Data Formatter and closes its black window. "
        "Anything you haven't downloaded yet will be lost."
    )
    close_column, cancel_column = st.columns(2)
    if close_column.button("Close the app", type="primary"):
        st.session_state["closing"] = True
        st.rerun()
    if cancel_column.button("Cancel"):
        st.rerun()


def _upload_key(name: str) -> str:
    """Widget key for an uploader, renewed by the sidebar's "start over" button."""
    return f"{name}_{st.session_state.get('upload_round', 0)}"


def _show_error(message: str, exc: Exception) -> None:
    """A plain-English error, with the technical text tucked away for support.

    A raw exception ("Worksheet named 'Accounts' not found", a KeyError) means
    nothing to the staff using this, but it is exactly what whoever supports
    them needs — so it is kept, just not in the headline.
    """
    st.error(message)
    with st.expander("Technical details (include these if you ask for help)"):
        st.code(f"{type(exc).__name__}: {exc}", language=None)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# The fields worth letting a user map by hand, with the plain-English label
# shown in the picker. Only these three fail every row when missing; the rest
# degrade gracefully, so cluttering the form with them would cost more than
# it gives.
_MAPPABLE_FIELDS = (
    ("airtime_phone", "Phone number"),
    ("network", "Network / provider"),
    ("amount", "Amount"),
)

_NOT_PRESENT = "— not in this file —"

# Validation issues name the canonical field, which is our word for it, not the
# user's. Anything unlisted falls through to the raw name rather than hiding.
_FIELD_LABELS = {
    **dict(_MAPPABLE_FIELDS),
    "account_name": "ID (Account Name)",
    "case_remark": "Case reference",
    "project_code": "Project code",
}


_ROW_PREFIX = re.compile(r"^Row \d+:\s*")


def _issue_table(issues: Sequence[ValidationIssue]) -> pd.DataFrame:
    """Validation issues as a table, with our field names put into theirs."""
    return pd.DataFrame(
        [
            {
                "Row": issue.row_number,
                "Column": _FIELD_LABELS.get(issue.field, issue.field),
                # Validator messages lead with "Row 5: …", which the Row column
                # already says.
                "Problem": _ROW_PREFIX.sub("", issue.message),
            }
            for issue in issues
        ]
    )


@st.cache_data(show_spinner="Preparing your file...")
def _prepare_upload(
    frame: pd.DataFrame, settings_json: str
) -> tuple[bytes | None, ValidationReport, int]:
    """Build the OpenFloat workbook, once per (frame, settings) combination.

    Without the cache this reruns on every keystroke in the Project code box,
    rewriting the whole workbook each time. Settings arrive as JSON because
    Streamlit hashes the arguments to decide what is a cache hit, and a
    Pydantic model is not something it knows how to hash.

    Deliberately **not** `persist="disk"`: the frame holds names, phone numbers
    and staff IDs, and that cache would write them under the user's home
    directory. In memory it lives exactly as long as the session does.
    """
    result = transform_frame(frame, Settings.model_validate_json(settings_json))
    return (
        result.output.getvalue() if result.output is not None else None,
        result.validation_report,
        result.output_row_count,
    )


def _select_columns(raw_df: pd.DataFrame) -> tuple[dict[str, str], str | None]:
    """One place to choose every column the pipeline reads.

    All four choices live together because they are the same decision from the
    user's side — "which of my columns is this?" — and splitting the identifier
    into its own always-visible section made a correct guess as loud as a wrong
    one. Detection pre-selects each dropdown, so a recognised file needs no
    interaction and this stays collapsed; it opens by itself when something is
    missing.

    The widgets are deliberately unkeyed — Streamlit derives their identity
    from their options, so uploading a different file resets the choices
    instead of carrying a stale column across.

    Returns:
        A tuple of (field → chosen column, identifier column or None). The
        identifier is None when left on auto-detect, which leaves
        `Settings.account_name_column` unset so detection runs per file.
    """
    detected, _ = resolve_input_columns(raw_df.columns)
    detected_id = find_account_name_column(raw_df.columns, frame=raw_df)
    missing = [label for field, label in _MAPPABLE_FIELDS if field not in detected]
    if detected_id is None:
        missing.append("Identifier")

    with st.expander(
        "Column mapping" + (f" — {len(missing)} not found" if missing else ""),
        expanded=bool(missing),
    ):
        st.caption(
            "Your export can name these columns anything. We guess from the "
            "header; correct any that are wrong."
        )
        columns = [str(column) for column in raw_df.columns]
        chosen: dict[str, str] = {}
        for field, label in _MAPPABLE_FIELDS:
            current = detected.get(field)
            # The sentinel is offered only when there is genuinely nothing to
            # point at. Selecting it for a column that was found used to drop
            # the field, let detection quietly find it again downstream, and
            # still show a red error saying every row would fail.
            options = columns if current in columns else [_NOT_PRESENT, *columns]
            selection = st.selectbox(
                label,
                options,
                index=options.index(current) if current in options else 0,
                help=f"Read as `{field}`",
            )
            if selection != _NOT_PRESENT:
                chosen[field] = selection

        id_options = [AUTO_DETECT, *(str(column) for column in raw_df.columns)]
        id_choice = st.selectbox(
            "Identifier (Account Name)",
            id_options,
            index=(
                id_options.index(str(detected_id))
                if detected_id is not None
                else 0
            ),
            help="Staff ID, Respondent ID, Case ID — whatever this export calls "
            "it. Written to the output 'Account Name' so a payment can be "
            "traced back to its source record.",
        )
        identifier = None if id_choice == AUTO_DETECT else id_choice

        # Sample values are the only way to catch a plausible-but-wrong
        # identifier — a column can score well and still hold the wrong thing.
        preview = identifier or (str(detected_id) if detected_id else None)
        if preview is not None:
            filled = [read_text_cell(cell) for cell in raw_df[preview]]
            non_empty = [value for value in filled if value]
            sample = ", ".join(non_empty[:3])
            st.caption(
                f"Account Name will use **{preview}** — {len(non_empty)}/"
                f"{len(raw_df)} rows have a value"
                f"{f' (e.g. {sample})' if sample else ''}"
            )
        else:
            st.caption(
                ":orange[No identifier column detected — Account Name will be "
                "blank for every row unless you pick one.]"
            )

        # Detection warnings describe guesses that are still standing, so
        # recompute them against whatever the user corrected — a column they
        # have already fixed should not keep warning about the original guess.
        corrected = {
            field: column
            for field, column in chosen.items()
            if column != detected.get(field)
        }
        _, live_warnings = resolve_input_columns(raw_df.columns, corrected)
        for warning in live_warnings:
            st.caption(f":orange[{warning}]")

    still_missing = [
        label for field, label in _MAPPABLE_FIELDS if field not in chosen
    ]
    if still_missing:
        st.error(
            "No column chosen for: "
            + ", ".join(f"**{label}**" for label in still_missing)
            + ". Every row will fail until you pick one under **Column mapping**."
        )
    return chosen, identifier


def _preview_remark(df: pd.DataFrame, config: Settings) -> None:
    """Show the Remark the first row will actually get, before anything downloads."""
    if df.empty:
        return
    result = build_remark(df.iloc[0], remark_context(df, config))
    if not result.remark:
        return
    readable = parse_case_remark(result.remark)[1] is None
    st.caption(
        f"Remark preview (row 1): `{result.remark}`"
        + ("" if readable else " — not a case reference the statement report can read")
    )


def _select_project_code(df: pd.DataFrame) -> str | None:
    """Show the project-code input and return what the user typed (or None).

    The code completes a short `C# 38305` case reference into the full
    `C#<case> <project_code> RESP AIRTIME-KSH<total> <activity>` Remark. A
    project-code column in the file wins per row; this is the fallback.
    """
    short_form_rows = count_short_form_rows(df)
    column = find_project_code_column(df.columns)
    if not short_form_rows and column is None:
        return None  # nothing to complete and nowhere to put it

    st.markdown("**Project code**")
    typed = st.text_input(
        "Project code for the case reference",
        value="",
        placeholder="e.g. 22505AA",
        help="Used to complete a short 'C# 38305' reference into the full Remark. "
        "A project_code column in the file takes precedence, row by row.",
    ).strip()

    if column is not None:
        st.caption(
            f"This file has a **{column}** column — it is used per row, and this box only "
            f"fills rows where it is blank."
        )
    if typed and " " in typed:
        st.warning(
            "A project code cannot contain spaces — the case reference would not be "
            "readable, so those rows would keep a short Remark."
        )
    elif short_form_rows and not typed and column is None:
        st.warning(
            f"{short_form_rows} row(s) carry a short case reference. Without a project code "
            f"their Remark stays short (e.g. `C#38305`)."
        )
    return typed or None


def render_transform_page(country_prefix: str, amount_threshold: int):
    """Upload → check columns → fix problems → download, as four numbered steps."""
    # --- Step 1: upload ---
    _step(1, "Upload your file")
    uploaded_file = st.file_uploader(
        "Your Process Maker airtime export (CSV or Excel)",
        type=["csv", "xlsx", "xls", "xlsm"],
        help="Drag the file here, or click Browse files to pick it.",
        key=_upload_key("transform_input"),
    )

    if uploaded_file is None:
        st.info(
            "Upload a file to get started. Filling one in by hand? Use "
            "`docs/processmaker-input-template.xlsx` in the app's folder — it "
            "has the right columns already."
        )
        return

    try:
        raw_df = read_input_file(uploaded_file, uploaded_file.name)
    except Exception as e:
        _show_error(
            "We couldn't open this file. Check it is the Process Maker export "
            "(CSV or Excel), that it isn't open in Excel right now, and try again.",
            e,
        )
        return

    if raw_df.empty:
        st.warning("This file has column headers but no rows. Is it the right file?")
        return

    # --- Step 2: columns ---
    # Exports rename these columns per run, so resolve them to the canonical
    # names before anything reads the frame. The picker pre-selects whatever
    # detection found and lets the user override it, which is what makes a
    # header nobody has seen before workable without a code change.
    _step(2, "Check the columns")
    column_choice, id_column = _select_columns(raw_df)
    df = canonicalize_input_columns(raw_df, column_choice)

    st.caption(
        f"Your file has **{len(df)} rows**. The first {min(len(df), 10)} are shown "
        "below so you can check it is the right file."
    )
    st.dataframe(df.head(10), hide_index=True)

    project_code = _select_project_code(df)

    config = Settings(
        max_amount_threshold=amount_threshold,
        default_country_prefix=country_prefix,
        account_name_column=id_column,
        project_code=project_code,
        openfloat_template_path=str(DEFAULT_TEMPLATE_PATH),
    )

    _preview_remark(df, config)

    # The frame on screen is the frame the workbook is built from — anything
    # that re-read the file here would drop the column choices made above.
    try:
        output_bytes, report, output_row_count = _prepare_upload(
            df, config.model_dump_json()
        )
    except Exception as e:
        _show_error(
            "Something went wrong while building the upload file. Nothing was "
            "downloaded. Try again, and if it keeps happening, ask for help.",
            e,
        )
        return

    # --- Step 3: problems ---
    _step(3, "Fix any problems")

    left_out = report.total_rows - report.valid_rows
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows in your file", report.total_rows, border=True)
    col2.metric("Ready for OpenFloat", report.valid_rows, border=True)
    col3.metric("Left out", left_out, border=True)

    if report.errors:
        with st.expander(
            f"Rows that will be left out ({len(report.errors)})",
            expanded=True,
            icon=":material/block:",
        ):
            st.caption(
                "Row numbers match the rows in your own spreadsheet. Fix these at "
                "the source, then upload the corrected file here again."
            )
            st.dataframe(_issue_table(report.errors), hide_index=True)
            st.download_button(
                label="Download the rows that need fixing",
                icon=":material/download:",
                data=write_rejected_rows_workbook(raw_df, report).getvalue(),
                file_name=Path(uploaded_file.name).stem + "_rows_to_fix.xlsx",
                mime=XLSX_MIME,
                help="Send this to whoever compiled the file — it has their own "
                "columns plus the reason each row was left out.",
            )

    counts = report.filtered_counts
    if counts.invalid_phone or counts.invalid_amount or counts.unmapped_network:
        with st.expander("Why rows were left out", expanded=False):
            if counts.invalid_phone:
                st.write(f"Invalid phone number: **{counts.invalid_phone}**")
            if counts.invalid_amount:
                st.write(f"Invalid amount: **{counts.invalid_amount}**")
            if counts.unmapped_network:
                st.write(f"Unrecognised network: **{counts.unmapped_network}**")

    if report.warnings:
        with st.expander(
            f"Worth checking ({len(report.warnings)})",
            expanded=False,
            icon=":material/warning:",
        ):
            st.caption(
                "These rows **are** in the upload file. Nothing is wrong for "
                "certain, but take a look (e.g. a very large amount, or the same "
                "phone number twice)."
            )
            st.dataframe(_issue_table(report.warnings), hide_index=True)

    if not report.errors and not report.warnings:
        st.success("Every row in this file can be uploaded.", icon=":material/check_circle:")

    # --- Step 4: download ---
    _step(4, "Download your upload file")

    if output_bytes is None:
        st.error(
            "There is nothing to download — every row was left out. Fix the rows "
            "above and upload the file again."
        )
        return

    # The easiest mistake here is uploading a partial file believing it is
    # complete, so say so right beside the button, not only up in Step 3.
    if left_out:
        st.warning(
            f"This file is **missing {left_out} row(s)** that had problems "
            "(see Step 3). Those people will not be paid unless their rows are "
            "fixed and sent separately."
        )
    st.download_button(
        label=f"Download {output_row_count} rows for OpenFloat",
        icon=":material/download:",
        data=output_bytes,
        file_name=Path(uploaded_file.name).stem + "_openfloat.xlsx",
        mime=XLSX_MIME,
        type="primary",
    )
    st.caption(
        "Next: upload this file to OpenFloat. When the disbursement finishes, "
        "download its Transaction Statement and come back to **Check payment "
        "results** to see what went through."
    )


def _download_name(statement_files: Sequence[Any], suffix: str, fallback: str) -> str:
    """Name the download after the statement when there is only one of them."""
    if len(statement_files) == 1:
        return Path(statement_files[0].name).stem + suffix
    return fallback


def _download_report(report: StatementReport, statement_files: Sequence[Any]) -> None:
    """Offer the two workbooks: the project leads' report, and the finance sheet."""
    report_column, finance_column = st.columns(2)
    # Both are filed by case, so they are named after the Remark when they can be.
    stem = remark_file_stem(report)

    with report_column:
        sheets = "Successful and Unsuccessful"
        if report.reconciliation is not None:
            sheets += ", plus the four reconciliation sheets"
        st.download_button(
            label="Statement Report (Excel)",
            icon=":material/download:",
            type="primary",
            width="stretch",
            data=write_statement_workbook(report).getvalue(),
            file_name=f"{stem}_report.xlsx" if stem else _download_name(
                statement_files, "_report.xlsx", "statement_report.xlsx"
            ),
            mime=XLSX_MIME,
        )
        st.caption(f"For project leads: {sheets} — each sheet totalled at the bottom.")

    with finance_column:
        st.download_button(
            label="Finance Reconciliation (Excel)",
            icon=":material/download:",
            type="primary",
            width="stretch",
            data=write_finance_workbook(report).getvalue(),
            file_name=f"{stem}.xlsx" if stem else _download_name(
                statement_files, "_finance.xlsx", "finance_reconciliation.xlsx"
            ),
            mime=XLSX_MIME,
        )
        st.caption(
            "Debit totals successful payments only; unsuccessful rows are shaded "
            "and excluded."
        )


def render_statement_report_page(country_prefix: str):
    """Statement Report: analyse OpenFloat Transaction Statement exports."""

    def _txn_display_columns(txn):
        return {
            "File": txn.file_name,
            "Row": txn.row_number,
            "Status": txn.status,
            "Phone": txn.account_number,
            "Account Name": txn.account_name,
            "Amount": txn.amount,
            "Reference Id": txn.reference_id,
            "Date": txn.date_raw,
            "Remark": txn.remark,
        }

    def _entry_display_columns(entry, bucket):
        return {
            "Result": bucket,
            "Phone": entry.phone,
            "ID": entry.unique_id,
            "Amount in your file": entry.input_amount,
            "Rows in your file": ", ".join(str(n) for n in entry.input_row_numbers),
            "Successful": entry.successful_count,
            "Unsuccessful": entry.unsuccessful_count,
            "Amount paid": entry.successful_total,
            "Notes": "; ".join(entry.notes),
        }

    _step(1, "Upload OpenFloat's statement")
    statement_files = st.file_uploader(
        "Transaction Statement file(s) downloaded from OpenFloat",
        type=["xlsx", "xls", "xlsm"],
        accept_multiple_files=True,
        help="You can select several at once if the disbursement was split.",
        key=_upload_key("statements"),
    )

    _step(2, "Add your original file", optional=True)
    pm_file = st.file_uploader(
        "The Process Maker export you prepared the upload from",
        type=["csv", "xlsx", "xls", "xlsm"],
        help="Add it to find people who were on your list but never paid.",
        key=_upload_key("statement_input"),
    )
    st.caption(
        "With this, the report also lists people who were on your list but "
        "never appeared on the statement."
    )

    if not statement_files:
        st.info("Upload at least one Transaction Statement to see the results.")
        return

    input_df = None
    if pm_file is not None:
        try:
            input_df = canonicalize_input_columns(read_input_file(pm_file, pm_file.name))
        except Exception as e:
            _show_error(
                "We couldn't open your Process Maker file. Check it is a CSV or "
                "Excel file and isn't open in Excel, or remove it to see the "
                "statement results on their own.",
                e,
            )
            return

    config = Settings(
        default_country_prefix=country_prefix,
        openfloat_template_path=str(DEFAULT_TEMPLATE_PATH),
    )

    with st.spinner("Building report..."):
        try:
            report = build_statement_report(
                [BytesIO(f.getvalue()) for f in statement_files],
                source_names=[f.name for f in statement_files],
                input_df=input_df,
                config=config,
            )
        except Exception as e:
            _show_error(
                "Something went wrong while reading the statement(s). Check they "
                "are the Transaction Statement files from OpenFloat and try again.",
                e,
            )
            return

    # --- Structural errors: reported, but the rest of the report still shows ---
    if report.errors:
        st.error(
            "Some files could not be read, so they are **not** included in the "
            "results below:\n\n" + "\n\n".join(f"- {error}" for error in report.errors)
        )

    if not report.transactions:
        st.warning(
            "No transactions were found. Check you uploaded OpenFloat's "
            "Transaction Statement, not the upload file or one of this app's reports."
        )
        return

    # --- Summary metrics ---
    _step(3, "Results")
    combined = report.combined
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Transactions", combined.total_rows, border=True)
    col2.metric("Successful", combined.successful_count, border=True)
    col3.metric("Unsuccessful", combined.unsuccessful_count, border=True)
    col4.metric("Paid out (KES)", f"{combined.total_disbursed:,.0f}", border=True)
    if combined.unsuccessful_count > 0:
        st.warning(
            f"**{combined.unsuccessful_count}** payment(s) did NOT go through. "
            "These people may need to be paid again — they are listed below."
        )

    # --- Unsuccessful transactions (the follow-up list) ---
    # First, because it is the one thing on this page someone has to act on.
    if report.unsuccessful_transactions:
        with st.expander(
            f"Payments that did not go through ({len(report.unsuccessful_transactions)})",
            expanded=True,
            icon=":material/error:",
        ):
            st.dataframe(
                pd.DataFrame(
                    [_txn_display_columns(txn) for txn in report.unsuccessful_transactions]
                ),
                hide_index=True,
            )
    else:
        st.success(
            "Every payment in every statement went through.", icon=":material/check_circle:"
        )

    # --- Download ---
    _step(4, "Download the reports")
    _download_report(report, statement_files)

    st.markdown("##### More detail")

    # --- Per-file summaries ---
    if report.file_summaries:
        # Worth opening by default only when there are several files to compare.
        with st.expander(
            "Each file",
            expanded=len(report.file_summaries) > 1,
            icon=":material/description:",
        ):
            summary_df = pd.DataFrame(
                [
                    {
                        "File": s.file_name,
                        "Rows": s.total_rows,
                        "Successful": s.successful_count,
                        "Unsuccessful": s.unsuccessful_count,
                        "Paid out (KES)": f"{s.total_disbursed:,.0f}",
                        "OpenFloat's own total": (
                            f"{s.footer_total:,.0f}" if s.footer_total is not None else "—"
                        ),
                        "Totals agree": (
                            "—" if s.footer_matches is None
                            else ("Yes" if s.footer_matches else "No")
                        ),
                    }
                    for s in report.file_summaries
                ]
            )
            st.dataframe(summary_df, hide_index=True)
        # Outside the expander: a total that disagrees must not hide in a
        # collapsed panel.
        for s in report.file_summaries:
            if s.footer_matches is False:
                st.warning(
                    f"**{s.file_name}**: OpenFloat's own total at the bottom of the "
                    f"file ({s.footer_total:,.0f}) does not match the successful "
                    f"payments we counted ({s.total_disbursed:,.0f}). Check the file "
                    "before relying on these figures."
                )

    # --- Status breakdown ---
    if len(combined.counts_by_status) > 1 or combined.unsuccessful_count > 0:
        with st.expander("Count by status", expanded=False):
            status_df = pd.DataFrame(
                [
                    {"Status": status, "Count": count}
                    for status, count in sorted(
                        combined.counts_by_status.items(), key=lambda kv: -kv[1]
                    )
                ]
            )
            st.dataframe(status_df, hide_index=True)

    # --- Per-case rollups ---
    with st.expander("Totals per case", expanded=False, icon=":material/folder:"):
        if report.case_rollups:
            rollup_df = pd.DataFrame(
                [
                    {
                        "Case #": r.case_number,
                        "Project": r.project_code or "—",
                        "Activity": r.activity_code or "—",
                        "Amount in reference": (
                            f"{r.remark_amount:,.0f}" if r.remark_amount is not None else "—"
                        ),
                        "Rows": r.total_rows,
                        "Successful": r.successful_count,
                        "Unsuccessful": r.unsuccessful_count,
                        "Paid out": f"{r.disbursed_total:,.0f}",
                        "Difference": (
                            f"{r.difference:,.0f}" if r.difference is not None else "—"
                        ),
                    }
                    for r in report.case_rollups
                ]
            )
            st.dataframe(rollup_df, hide_index=True)
        else:
            st.info("No case references (C#...) could be read from the Remark column.")
    # Outside the expander, like the footer check: a case that was over- or
    # under-paid is a finding, not a detail.
    for r in report.case_rollups:
        # None (short-form remark, no amount to compare) and 0 both mean
        # "nothing to flag".
        if r.difference:
            st.warning(
                f"**Case #{r.case_number}**: the case reference says KES "
                f"{r.remark_amount:,.0f}, but KES {r.disbursed_total:,.0f} was "
                f"actually paid out (difference {r.difference:,.0f})."
            )

    # --- Reconciliation (only when an input file was supplied) ---
    if report.reconciliation is not None:
        st.markdown("##### Compared with your Process Maker file")
        rec = report.reconciliation
        buckets = [
            ("Paid", rec.matched_paid),
            ("On the statement, not paid", rec.matched_not_paid),
            ("In your file, not on the statement", rec.missing_from_statement),
            ("On the statement, not in your file", rec.statement_not_in_input),
        ]
        for column, (label, entries) in zip(st.columns(4), buckets, strict=True):
            column.metric(label, len(entries), border=True)
        if rec.missing_from_statement:
            st.warning(
                f"**{len(rec.missing_from_statement)}** phone number(s) in your file "
                "are not on any statement you uploaded, so there is no record of "
                "them being paid. Were their rows left out of the upload, or is a "
                "statement file missing?"
            )

        for label, entries in buckets:
            if entries:
                with st.expander(f"{label} ({len(entries)})", expanded=False):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                _entry_display_columns(entry, label)
                                for entry in entries
                            ]
                        ),
                        hide_index=True,
                    )

        if rec.duplicate_input_phones:
            st.warning(
                "The same phone number appears more than once in your file: "
                + ", ".join(rec.duplicate_input_phones)
            )
        if rec.multiply_paid_phones:
            st.warning(
                "These phone numbers were paid more than once: "
                + ", ".join(rec.multiply_paid_phones)
            )

    # --- Parse warnings ---
    if report.warnings:
        with st.expander(
            f"Rows we could not fully read ({len(report.warnings)})",
            expanded=False,
            icon=":material/warning:",
        ):
            st.dataframe(pd.DataFrame({"Warning": report.warnings}), hide_index=True)


if __name__ == "__main__":
    main()
