"""Streamlit UI for the OpenFloat Data Formatter.

Provides a simple web interface for non-technical staff to:
1. Upload a Process Maker CSV/Excel file
2. Preview the data and validation report
3. Download the transformed OpenFloat-ready Excel file
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure src is importable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DEFAULT_TEMPLATE_PATH, Settings
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

    # --- Sidebar: Configuration ---
    st.sidebar.header("Configuration")
    amount_threshold = st.sidebar.number_input(
        "Max amount threshold (KES)",
        min_value=0,
        value=10_000,
        help="Warn when airtime amount exceeds this value",
    )
    country_prefix = st.sidebar.text_input(
        "Country prefix",
        value="254",
        help="Country code prepended to phone numbers",
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


if __name__ == "__main__":
    main()