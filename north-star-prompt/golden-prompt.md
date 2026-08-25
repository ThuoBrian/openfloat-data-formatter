# 🌟 OpenFloat Data Formatter — Golden Prompt

> The single source-of-truth specification for building the Airtime Data Formatter (ADF).  
> Every design decision, data contract, and acceptance criterion is captured here.  
> If it's not in this document, it's not in scope.

---

## 1. Problem Statement

Staff currently download airtime disbursement data from **Process Maker** as a CSV/Excel file, then manually reformat, validate, and upload it into **OpenFloat SaaS**. This manual process is:

- **Error-prone** — phone numbers get mangled, amounts mistyped, account types miscategorized.
- **Slow** — each batch requires repetitive copy-paste formatting.
- **Opaque** — no audit trail, no validation feedback, no error recovery.

The ADF eliminates this by automating the transformation pipeline from Process Maker export → OpenFloat-ready upload.

---

## 2. Input Contract — Process Maker Export

The tool accepts CSV or Excel files exported from Process Maker with these columns:

| Column | Type | Example | Notes |
|---|---|---|---|
| `unique_id` | string | `159UECASBW` | Row-level identifier from Process Maker |
| `consent` | string | `Yes` | Must be `"Yes"` to proceed |
| `airtime_phone` | string | `785271309` | 9-digit local number (no country code prefix) |
| `network` | string | `Safaricom` \| `Airtel` | Maps to OpenFloat account type |
| `submissiondate` | datetime | `8/17/2026 13:10` | When the request was submitted |
| `today` | string | `17aug2026` | Submission date shorthand |
| `amount` | string/number | `150` | Airtime amount in KES |
| `project_name` | string | `BMG-25-20360 22505AA Kenya` | Project identifier |
| `Project_Activity` | string | `g05\|Respondent Gifts` | Activity code and description (pipe-delimited) |
| `department` | string | `Projects` | Organizational unit |
| `survey` | string | `Baseline` | Survey phase |

### Input Assumptions

- The file may contain rows where `consent ≠ "Yes"`. These must be **filtered out**.
- Phone numbers may arrive with or without the `254` country prefix; the tool must normalize to 9 digits.
- `amount` may be stored as a string; coerce to numeric and reject non-numeric values.
- `network` values are free-text; map them to the OpenFloat account types (see §3).

---

## 3. Output Contract — OpenFloat Template

The tool must produce an Excel file matching the **OpenFloat Transactions Template** with two sheets:

### 3.1 Sheet: `Accounts`

| Column | Type | Required | Description |
|---|---|---|---|
| `Account Type` | string | ✅ | Must be one of the **Allowed Types** (see §3.2). For airtime: `Safaricom Prepaid`, `Airtel Prepaid`, `Airtel Postpaid`, `Telkom Kenya Prepaid`, `Telkom Kenya Postpaid` |
| `Account Name` | string | ✅ | The `unique_id` from Process Maker (e.g., `159UECASBW`) |
| `Account Number` | string | ✅ | The normalized phone number with `254` prefix (e.g., `254785271309`) |
| `Till or Paybill Number` | string | ❌ | Blank for airtime |
| `Till or Paybill Business Name` | string | ❌ | Blank for airtime |
| `Notification Phone Number` | string | ✅ | Same as Account Number (the recipient gets the notification) |
| `Amount` | number | ✅ | Airtime amount in KES (e.g., `150`) |
| `Remark` | string | ❌ | Optional: `{project_name} - {Project_Activity}` (e.g., `BMG-25-20360 22505AA Kenya - g05|Respondent Gifts`) |

### 3.2 Sheet: `Allowed Types`

Pre-populated with OpenFloat's master list. The tool must **not** modify this sheet. Key airtime-relevant types:

- `Safaricom Prepaid`
- `Airtel Prepaid`
- `Airtel Postpaid`
- `Telkom Kenya Prepaid`
- `Telkom Kenya Postpaid`

Full list (62 types) is defined in the reference template at `docs/openfloat-transactions-template.xlsx` and must be copied verbatim.

---

## 4. Transformation Logic

### 4.1 Network → Account Type Mapping

| Process Maker `network` | OpenFloat `Account Type` |
|---|---|
| `Safaricom` | `Safaricom Prepaid` |
| `Airtel` | `Airtel Prepaid` |
| `Airtel Postpaid` | `Airtel Postpaid` |
| `Telkom` | `Telkom Kenya Prepaid` |
| `Telkom Postpaid` | `Telkom Kenya Postpaid` |

> **Unmapped networks** → raise a validation error listing the unrecognized value(s).

### 4.2 Phone Number Normalization

1. Strip whitespace and special characters (`-`, `(`, `)`, `+`).
2. If the number starts with `254`, remove the prefix → keep the remaining 9 digits.
3. If the number starts with `0`, remove the leading zero → keep 9 digits.
4. Prepend `254` for the `Account Number` and `Notification Phone Number` fields.
5. **Reject** numbers that are not exactly 9 digits after stripping (after removing a valid prefix).

### 4.3 Filtering Rules

- **Consent filter**: Exclude rows where `consent ≠ "Yes"` (case-insensitive).
- **Duplicate detection**: Warn if the same `airtime_phone` appears more than once in a batch. Do not silently deduplicate — surface the duplicates for user review.

### 4.4 Amount Validation

- Coerce `amount` to a positive number.
- Reject rows where `amount ≤ 0` or is non-numeric.
- Warn if `amount` exceeds a configurable threshold (default: KES 10,000 per transaction).

---

## 5. Architecture

```
openfloat-data-formatter/
├── src/
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── transformer.py       # Core transformation logic (pandas)
│   │   ├── validator.py         # Input validation & error collection
│   │   ├── normalizer.py        # Phone number & field normalization
│   │   ├── mapper.py            # Network → Account Type mapping
│   │   ├── writer.py            # Excel output generation (openpyxl)
│   │   ├── api_client.py        # OpenFloat API integration (future)
│   │   ├── config.py            # Settings, thresholds, mapping tables
│   │   └── models.py            # Pydantic data models
│   ├── frontend/
│   │   └── app.py               # Streamlit UI (optional)
│   └── tests/
│       ├── test_transformer.py
│       ├── test_validator.py
│       ├── test_normalizer.py
│       ├── test_mapper.py
│       ├── test_writer.py
│       └── conftest.py          # Shared fixtures
├── docs/
│   ├── openfloat-transactions-template.xlsx   # Reference template
│   ├── 1_ProcessMaker_Bridges_Combined_Airtime_Report.csv  # Sample input
│   └── Final_Report_11364-260825073447.xlsx    # Sample output reference
├── north-star-prompt/
│   └── golden-prompt.md         # This file
├── requirements.txt
├── Dockerfile
└── README.md
```

### Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Data processing | Python 3.11+, Pandas | CSV/Excel ingestion & transformation |
| Excel output | OpenPyXL | Write OpenFloat-formatted `.xlsx` |
| API | FastAPI | REST endpoints for programmatic use |
| UI | Streamlit | Optional web interface for non-technical staff |
| Validation | Pydantic v2 | Data models & schema validation |
| Containerization | Docker | Reproducible deployment |

---

## 6. API Design (FastAPI)

### `POST /transform`

Upload a Process Maker CSV/Excel and receive a transformed OpenFloat-ready Excel file.

**Request**: `multipart/form-data` with file upload  
**Response**: Binary `.xlsx` file download

### `POST /validate`

Upload a file and receive a validation report (no transformation).

**Request**: `multipart/form-data` with file upload  
**Response**: JSON

```json
{
  "total_rows": 196,
  "valid_rows": 190,
  "filtered_rows": {
    "consent_filtered": 4,
    "invalid_phone": 1,
    "invalid_amount": 1
  },
  "warnings": [
    "Row 42: Duplicate phone number 254712345678 also appears on rows 43, 44"
  ],
  "errors": [
    "Row 55: Unrecognized network 'Orange'",
    "Row 88: Amount 'abc' is not numeric"
  ]
}
```

### `POST /push` *(future)*

Transform and push directly to OpenFloat API.

---

## 7. Acceptance Criteria

| # | Criterion | Priority |
|---|---|---|
| AC-1 | Upload a Process Maker CSV → receive a valid OpenFloat `.xlsx` with `Accounts` and `Allowed Types` sheets | P0 |
| AC-2 | All `consent ≠ "Yes"` rows are excluded from output | P0 |
| AC-3 | Phone numbers are normalized to `254XXXXXXXXX` format | P0 |
| AC-4 | `network` values are correctly mapped to OpenFloat account types | P0 |
| AC-5 | Unmapped networks produce clear error messages | P0 |
| AC-6 | Invalid/non-numeric amounts are rejected with row-level errors | P0 |
| AC-7 | Duplicate phone numbers are flagged as warnings | P1 |
| AC-8 | Amounts above threshold (default KES 10,000) are flagged as warnings | P1 |
| AC-9 | The `Allowed Types` sheet is copied verbatim from the reference template | P0 |
| AC-10 | `/validate` endpoint returns a detailed report without transforming | P1 |
| AC-11 | Streamlit UI allows file upload, preview, and download | P2 |
| AC-12 | Docker container builds and runs the full stack | P2 |

---

## 8. Error Handling

The tool must never silently drop or modify data. Instead:

1. **Collect all issues** in a validation report before transformation.
2. **Hard errors** (unmapped network, invalid amount, bad phone format) → exclude the row, report it.
3. **Soft warnings** (duplicates, high amounts) → include the row, surface the warning.
4. Provide a **row-level error map** so users can fix issues in their source data.

---

## 9. Configuration

All tuneable values live in `src/backend/config.py` (or `.env` for secrets):

| Setting | Default | Description |
|---|---|---|
| `MAX_AMOUNT_THRESHOLD` | `10000` | Warn on amounts above this value (KES) |
| `DEFAULT_COUNTRY_PREFIX` | `254` | Country code prepended to phone numbers |
| `REQUIRED_CONSENT_VALUE` | `"Yes"` | Value that grants inclusion (case-insensitive) |
| `NETWORK_MAP` | (see §4.1) | Mapping from Process Maker network names to OpenFloat account types |

---

## 10. Future Considerations

- **OpenFloat API push**: Direct submission via REST API (requires auth credentials).
- **Batch management**: Track multiple transformation runs, store logs in SQLite.
- **Template versioning**: Detect and adapt if OpenFloat changes the template format.
- **Multi-network support**: Extend beyond Safaricom/Airtel to all 62+ account types in the Allowed Types sheet.
- **Audit trail**: Log every transformation with input hash, row counts, and output checksum.