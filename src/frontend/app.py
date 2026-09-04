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

from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure src is importable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DEFAULT_TEMPLATE_PATH, Settings
from backend.statement import build_statement_report
from backend.transformer import transform
from backend.validator import validate


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
    consent_value = st.sidebar.text_input(
        'Required consent value',
        value="Yes",
        help='Rows with this consent value are included (case-insensitive)',
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
        if suffix == ".csv":
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return

    # --- Preview ---
    st.header("Data Preview")
    st.markdown(f"**{len(df)} rows** × **{len(df.columns)} columns**")
    st.dataframe(df.head(10), use_container_width=True)

    # --- Configuration ---
    config = Settings(
        max_amount_threshold=amount_threshold,
        default_country_prefix=country_prefix,
        required_consent_value=consent_value,
        openfloat_template_path=str(DEFAULT_TEMPLATE_PATH),
    )

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
    if report.filtered_counts.consent_filtered > 0 or \
       report.filtered_counts.invalid_phone > 0 or \
       report.filtered_counts.invalid_amount > 0 or \
       report.filtered_counts.unmapped_network > 0:
        with st.expander("Filter Breakdown", expanded=True):
            if report.filtered_counts.consent_filtered > 0:
                st.write(f"🚫 Consent filtered: **{report.filtered_counts.consent_filtered}**")
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
                input_df = pd.read_csv(pm_file)
            else:
                input_df = pd.read_excel(pm_file)
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
                [f.getvalue() for f in statement_files],
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
                        "Project": r.project_code,
                        "Activity": r.activity_code,
                        "Remark Amount": f"{r.remark_amount:,.0f}",
                        "Rows": r.total_rows,
                        "Successful": r.successful_count,
                        "Unsuccessful": r.unsuccessful_count,
                        "Disbursed": f"{r.disbursed_total:,.0f}",
                        "Difference": f"{r.difference:,.0f}",
                    }
                    for r in report.case_rollups
                ]
            )
            st.dataframe(rollup_df, use_container_width=True)
            for r in report.case_rollups:
                if r.difference != 0:
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