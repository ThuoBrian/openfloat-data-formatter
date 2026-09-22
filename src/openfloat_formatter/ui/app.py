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

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from openfloat_formatter.config import DEFAULT_TEMPLATE_PATH, Settings
from openfloat_formatter.models import StatementReport
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
from openfloat_formatter.transformer import transform
from openfloat_formatter.validator import remark_context, validate
from openfloat_formatter.writer import write_finance_workbook, write_statement_workbook


def main():
    st.set_page_config(
        page_title="OpenFloat Data Formatter",
        page_icon="🔄",
        layout="wide",
    )

    st.title("🔄 OpenFloat Data Formatter")
    st.markdown(
        "Transform Process Maker airtime exports into OpenFloat-ready uploads."
    )

    # --- Sidebar: mode selection + shared configuration ---
    mode = st.sidebar.radio(
        "Mode",
        ["Transform", "Statement Report"],
        horizontal=True,
        help="Transform builds OpenFloat uploads; Statement Report analyses "
        "the statements OpenFloat produced after a disbursement",
    )
    country_prefix = st.sidebar.text_input(
        "Country prefix",
        value="254",
        help="Country code prepended to phone numbers",
    )

    if mode == "Transform":
        render_transform_page(country_prefix)
    else:
        render_statement_report_page(country_prefix)


AUTO_DETECT = "(auto-detect)"


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
        options = [_NOT_PRESENT, *(str(column) for column in raw_df.columns)]
        chosen: dict[str, str] = {}
        for field, label in _MAPPABLE_FIELDS:
            current = detected.get(field)
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

    st.header("Project Code")
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


def render_transform_page(country_prefix: str):
    """Existing pipeline: upload → validate → transform → download."""
    # --- Sidebar: transform-specific configuration ---
    st.sidebar.header("Configuration")
    amount_threshold = st.sidebar.number_input(
        "Max amount threshold (KES)",
        min_value=0,
        value=10_000,
        help="Warn when airtime amount exceeds this value",
    )
    # --- File Upload ---
    st.header("Upload Process Maker File")
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls", "xlsm"],
        help="Upload a Process Maker airtime disbursement export",
    )

    if uploaded_file is None:
        st.info("Upload a file to get started.")
        return

    # --- Read file ---
    try:
        suffix = Path(uploaded_file.name).suffix.lower()
        raw_df = (
            pd.read_csv(uploaded_file)
            if suffix == ".csv"
            else pd.read_excel(uploaded_file)
        )
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return

    # Exports rename these columns per run, so resolve them to the canonical
    # names before anything reads the frame. The picker pre-selects whatever
    # detection found and lets the user override it, which is what makes a
    # header nobody has seen before workable without a code change.
    column_choice, id_column = _select_columns(raw_df)
    df = canonicalize_input_columns(raw_df, column_choice)

    # --- Preview ---
    st.header("Data Preview")
    st.markdown(f"**{len(df)} rows** × **{len(df.columns)} columns**")
    st.dataframe(df.head(10), use_container_width=True)

    project_code = _select_project_code(df)

    # --- Configuration ---
    config = Settings(
        max_amount_threshold=amount_threshold,
        default_country_prefix=country_prefix,
        account_name_column=id_column,
        project_code=project_code,
        openfloat_template_path=str(DEFAULT_TEMPLATE_PATH),
    )

    _preview_remark(df, config)

    # --- Validate ---
    st.header("Validation Report")

    with st.spinner("Validating..."):
        report = validate(df, config)

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rows", report.total_rows)
    col2.metric("Valid Rows", report.valid_rows)
    col3.metric("Filtered Rows", report.total_rows - report.valid_rows)

    # Filtered breakdown
    if report.filtered_counts.invalid_phone > 0 or \
       report.filtered_counts.invalid_amount > 0 or \
       report.filtered_counts.unmapped_network > 0:
        with st.expander("Filter Breakdown", expanded=True):
            if report.filtered_counts.invalid_phone > 0:
                st.write(f"📞 Invalid phone: **{report.filtered_counts.invalid_phone}**")
            if report.filtered_counts.invalid_amount > 0:
                st.write(f"💰 Invalid amount: **{report.filtered_counts.invalid_amount}**")
            if report.filtered_counts.unmapped_network > 0:
                st.write(f"📡 Unmapped network: **{report.filtered_counts.unmapped_network}**")

    # Errors
    if report.errors:
        with st.expander(f"❌ Errors ({len(report.errors)})", expanded=False):
            error_df = pd.DataFrame(
                [
                    {
                        "Row": e.row_number,
                        "Field": e.field,
                        "Message": e.message,
                    }
                    for e in report.errors
                ]
            )
            st.dataframe(error_df, use_container_width=True)

    # Warnings
    if report.warnings:
        with st.expander(f"⚠️ Warnings ({len(report.warnings)})", expanded=False):
            warning_df = pd.DataFrame(
                [
                    {
                        "Row": w.row_number,
                        "Field": w.field,
                        "Message": w.message,
                    }
                    for w in report.warnings
                ]
            )
            st.dataframe(warning_df, use_container_width=True)

    if not report.errors and not report.warnings:
        st.success("✅ All rows are valid!")

    # --- Transform & Download ---
    st.header("Transform & Download")

    # Save uploaded file to a temp location for the transformer
    with st.spinner("Transforming..."):
        import tempfile

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix
        ) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            result = transform(tmp_path, config)
        except Exception as e:
            st.error(f"Transformation error: {e}")
            return
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    if result.output is not None:
        result.output.seek(0)
        output_filename = Path(uploaded_file.name).stem + "_openfloat.xlsx"

        st.download_button(
            label="📥 Download OpenFloat Excel",
            data=result.output.getvalue(),
            file_name=output_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.info(f"**{result.output_row_count} rows** written to the Accounts sheet.")
    else:
        st.error("No output was generated. All rows were filtered out due to errors.")


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download_name(statement_files: Sequence[Any], suffix: str, fallback: str) -> str:
    """Name the download after the statement when there is only one of them."""
    if len(statement_files) == 1:
        return Path(statement_files[0].name).stem + suffix
    return fallback


def _download_report(report: StatementReport, statement_files: Sequence[Any]) -> None:
    """Offer the two workbooks: the full report, and the finance sheet."""
    report_column, finance_column = st.columns(2)

    with report_column:
        sheets = "Successful and Unsuccessful"
        if report.reconciliation is not None:
            sheets += ", plus the four reconciliation sheets"
        st.download_button(
            label="📥 Download Statement Report (Excel)",
            data=write_statement_workbook(report).getvalue(),
            file_name=_download_name(statement_files, "_report.xlsx", "statement_report.xlsx"),
            mime=XLSX_MIME,
        )
        st.caption(f"{sheets} — each sheet totalled at the bottom.")

    with finance_column:
        st.download_button(
            label="💰 Download Finance Reconciliation (Excel)",
            data=write_finance_workbook(report).getvalue(),
            file_name=_download_name(
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
            "Bucket": bucket,
            "Phone": entry.phone,
            "Unique ID": entry.unique_id,
            "Input Amount": entry.input_amount,
            "Input Rows": ", ".join(str(n) for n in entry.input_row_numbers),
            "Successful": entry.successful_count,
            "Unsuccessful": entry.unsuccessful_count,
            "Paid Total": entry.successful_total,
            "Notes": "; ".join(entry.notes),
        }

    st.header("📊 OpenFloat Statement Report")
    st.markdown(
        "Report on successful and unsuccessful disbursements from OpenFloat "
        "Transaction Statement exports. Upload the original Process Maker "
        "input too to find beneficiaries who were never paid."
    )

    statement_files = st.file_uploader(
        "Statement exports",
        type=["xlsx", "xls", "xlsm"],
        accept_multiple_files=True,
        help="One or more 'Transaction Statement' files downloaded from OpenFloat",
    )
    pm_file = st.file_uploader(
        "Process Maker input (optional — enables reconciliation)",
        type=["csv", "xlsx", "xls", "xlsm"],
        help="The original Process Maker export that was uploaded to OpenFloat",
    )

    if not statement_files:
        st.info("Upload one or more statement exports to get started.")
        return

    input_df = None
    if pm_file is not None:
        try:
            if Path(pm_file.name).suffix.lower() == ".csv":
                input_df = canonicalize_input_columns(pd.read_csv(pm_file))
            else:
                input_df = canonicalize_input_columns(pd.read_excel(pm_file))
        except Exception as e:
            st.error(f"Error reading Process Maker input: {e}")
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
            st.error(f"Statement report error: {e}")
            return

    # --- Structural errors: reported, but the rest of the report still shows ---
    if report.errors:
        st.error("Some statements could not be parsed:\n\n" + "\n\n".join(report.errors))

    if not report.transactions:
        st.warning("No transactions were found in any statement.")
        return

    # --- Summary metrics ---
    combined = report.combined
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Transactions", combined.total_rows)
    col2.metric("✅ Successful", combined.successful_count)
    col3.metric("❌ Unsuccessful", combined.unsuccessful_count)
    col4.metric("Success Rate", f"{combined.success_rate:.1%}")
    col5.metric("Total Disbursed (KES)", f"{combined.total_disbursed:,.0f}")
    if combined.unsuccessful_count > 0:
        st.warning(
            f"**{combined.unsuccessful_count}** transaction(s) were NOT successful "
            "and may need follow-up or re-disbursement — see the unsuccessful list below."
        )

    # --- Download ---
    # Placed before the expanders so the follow-up list is one click away rather
    # than at the bottom of the whole report.
    _download_report(report, statement_files)

    # --- Per-file summaries ---
    if len(report.file_summaries) > 1 or report.file_summaries:
        with st.expander("📁 File Summaries", expanded=True):
            summary_df = pd.DataFrame(
                [
                    {
                        "File": s.file_name,
                        "Rows": s.total_rows,
                        "Successful": s.successful_count,
                        "Unsuccessful": s.unsuccessful_count,
                        "Disbursed (KES)": f"{s.total_disbursed:,.0f}",
                        "Footer Total": (
                            f"{s.footer_total:,.0f}" if s.footer_total is not None else "—"
                        ),
                        "Footer Matches": (
                            "—" if s.footer_matches is None
                            else ("✅ Yes" if s.footer_matches else "❌ No")
                        ),
                        "Success Rate": f"{s.success_rate:.1%}",
                    }
                    for s in report.file_summaries
                ]
            )
            st.dataframe(summary_df, use_container_width=True)
            for s in report.file_summaries:
                if s.footer_matches is False:
                    st.warning(
                        f"**{s.file_name}**: the footer total ({s.footer_total:,.0f}) does "
                        f"not match the computed successful total ({s.total_disbursed:,.0f})."
                    )

    # --- Status breakdown ---
    if len(combined.counts_by_status) > 1 or combined.unsuccessful_count > 0:
        with st.expander("Status Breakdown", expanded=False):
            status_df = pd.DataFrame(
                [
                    {"Status": status, "Count": count}
                    for status, count in sorted(
                        combined.counts_by_status.items(), key=lambda kv: -kv[1]
                    )
                ]
            )
            st.dataframe(status_df, use_container_width=True)

    # --- Unsuccessful transactions (the follow-up list) ---
    if report.unsuccessful_transactions:
        with st.expander(
            f"❌ Unsuccessful Transactions ({len(report.unsuccessful_transactions)})",
            expanded=True,
        ):
            st.dataframe(
                pd.DataFrame(
                    [_txn_display_columns(txn) for txn in report.unsuccessful_transactions]
                ),
                use_container_width=True,
            )
    else:
        st.success("✅ Every transaction in every statement was successful.")

    # --- Per-case rollups ---
    with st.expander("🗂️ Per-Case Summary", expanded=False):
        if report.case_rollups:
            rollup_df = pd.DataFrame(
                [
                    {
                        "Case #": r.case_number,
                        "Project": r.project_code or "—",
                        "Activity": r.activity_code or "—",
                        "Remark Amount": (
                            f"{r.remark_amount:,.0f}" if r.remark_amount is not None else "—"
                        ),
                        "Rows": r.total_rows,
                        "Successful": r.successful_count,
                        "Unsuccessful": r.unsuccessful_count,
                        "Disbursed": f"{r.disbursed_total:,.0f}",
                        "Difference": (
                            f"{r.difference:,.0f}" if r.difference is not None else "—"
                        ),
                    }
                    for r in report.case_rollups
                ]
            )
            st.dataframe(rollup_df, use_container_width=True)
            for r in report.case_rollups:
                # None (short-form remark, no amount to compare) and 0 both mean
                # "nothing to flag".
                if r.difference:
                    st.warning(
                        f"**Case #{r.case_number} ({r.project_code})**: KSH {r.difference:,.0f} "
                        f"difference between the remark amount ({r.remark_amount:,.0f}) and "
                        f"what was actually disbursed ({r.disbursed_total:,.0f})."
                    )
        else:
            st.info("No parseable case remarks were found.")

    # --- Reconciliation (only when an input file was supplied) ---
    if report.reconciliation is not None:
        st.subheader("🔍 Reconciliation vs Process Maker Input")
        rec = report.reconciliation
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Paid", len(rec.matched_paid))
        col2.metric("Matched but Unpaid", len(rec.matched_not_paid))
        col3.metric("Missing from Statement", len(rec.missing_from_statement))
        col4.metric("Not in Input", len(rec.statement_not_in_input))

        buckets = [
            ("✅ Matched & Paid", rec.matched_paid),
            ("❌ Matched but Unpaid", rec.matched_not_paid),
            ("🚫 Missing from Statement", rec.missing_from_statement),
            ("❓ Statement Rows Not in Input", rec.statement_not_in_input),
        ]
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
                        use_container_width=True,
                    )

        if rec.duplicate_input_phones:
            st.warning(
                f"Duplicate phone(s) in the input file: {', '.join(rec.duplicate_input_phones)}"
            )
        if rec.multiply_paid_phones:
            st.warning(
                f"Phone(s) paid more than once in the statements: "
                f"{', '.join(rec.multiply_paid_phones)}"
            )

    # --- Parse warnings ---
    if report.warnings:
        with st.expander(f"⚠️ Parse Warnings ({len(report.warnings)})", expanded=False):
            st.dataframe(
                pd.DataFrame({"Warning": report.warnings}),
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
