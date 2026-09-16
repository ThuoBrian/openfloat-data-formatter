"""Shared test helpers.

Synthetic statement data only. The real exports in sample_report_output/ hold
staff names and phone numbers and are never read by a test.
"""

GOOD_DATE = "24/08/2026 02:56:42 PM"
GOOD_REMARK = "C#37154 13054AF RESP AIRTIME-KSH27900 d05"


def statement_row(
    status="Successful",
    phone=254712345678,
    amount=100,
    remark=GOOD_REMARK,
    **overrides,
):
    """A default statement data row; keyword args override any header column."""
    row = {
        "Approval Id": 14886185,
        "Transaction Id": 18488654,
        "Transaction Type": "Payment",
        "Transaction Status": status,
        "Date": GOOD_DATE,
        "Account Name": 9019830,
        "Account Number": phone,
        "Account Type": "Partner",
        "Remark": remark,
        "Initiated By": "Test User",
        "Approved/Rejected By": "Test Approver",
        "Amount": amount,
    }
    row.update(overrides)
    return row
