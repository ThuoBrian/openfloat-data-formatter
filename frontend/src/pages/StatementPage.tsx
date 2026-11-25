/**
 * "Check payment results": read OpenFloat's Transaction Statement(s), say who
 * was and wasn't paid, and optionally reconcile against the Process Maker file.
 *
 * Findings that need action (a failed payment, a total that disagrees, a case
 * paid more or less than its reference says) are shown in the open. Detail
 * sits in collapsed panels.
 */
import { useEffect, useState } from "react";

import {
  ApiError,
  MAX_UPLOAD_BYTES,
  buildStatementReport,
  downloadWorkbook,
  statementForm,
  statementWorkbookPath,
  type ReconciliationEntry,
  type StatementReport,
  type StatementTransaction,
  type StatementWorkbook,
} from "../api/client";
import {
  DataTable,
  ErrorNotice,
  FileDrop,
  Metric,
  MetricRow,
  Notice,
  SettingsBlocked,
  Step,
} from "../components/ui";

export interface StatementSettings {
  /** A sidebar setting is invalid: keep the files, but don't run until it's fixed. */
  blocked: boolean;
  countryPrefix: string;
}

const KES = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Whole shillings with thousands separators, or a dash when there is no figure. */
function kes(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : KES.format(value);
}

/** An amount cell: blank when the statement has none (a Reversed row). */
function amountCell(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : KES.format(value);
}

const TRANSACTION_COLUMNS = ["File", "Row", "Status", "Phone", "Account Name", "Amount", "Reference Id", "Date", "Remark"];

function transactionRows(transactions: StatementTransaction[]): string[][] {
  return transactions.map((t) => [
    t.file_name ?? "",
    String(t.row_number ?? ""),
    t.status ?? "",
    t.account_number ?? "",
    t.account_name ?? "",
    amountCell(t.amount),
    t.reference_id ?? "",
    t.date_raw ?? "",
    t.remark ?? "",
  ]);
}

const ENTRY_COLUMNS = [
  "Result",
  "Phone",
  "ID",
  "Amount in your file",
  "Rows in your file",
  "Successful",
  "Unsuccessful",
  "Amount paid",
  "Notes",
];

function entryRows(entries: ReconciliationEntry[], bucket: string): string[][] {
  return entries.map((entry) => [
    bucket,
    entry.phone,
    entry.unique_id ?? "",
    amountCell(entry.input_amount),
    (entry.input_row_numbers ?? []).join(", "),
    String(entry.successful_count ?? 0),
    String(entry.unsuccessful_count ?? 0),
    KES.format(entry.successful_total ?? 0),
    (entry.notes ?? []).join("; "),
  ]);
}

export function StatementPage({ settings }: { settings: StatementSettings }) {
  const [statements, setStatements] = useState<File[]>([]);
  const [input, setInput] = useState<File | null>(null);
  const [report, setReport] = useState<StatementReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tooBig, setTooBig] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<unknown>(null);

  useEffect(() => {
    setReport(null);
    if (statements.length === 0 || settings.blocked) return;
    const controller = new AbortController();
    setError(null);
    buildStatementReport(statementForm(statements, input, settings.countryPrefix), controller.signal)
      .then(setReport)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught);
      });
    return () => controller.abort();
  }, [statements, input, settings.countryPrefix, settings.blocked]);

  /** Refuse an oversized file here rather than send it and get a 413. */
  function withinLimit(files: File[]): boolean {
    const big = files.find((file) => file.size > MAX_UPLOAD_BYTES);
    setTooBig(big ? big.name : null);
    return big === undefined;
  }

  async function download(kind: StatementWorkbook, fallback: string) {
    setDownloadError(null);
    try {
      await downloadWorkbook(
        statementWorkbookPath(kind),
        statementForm(statements, input, settings.countryPrefix),
        fallback,
      );
    } catch (caught) {
      setDownloadError(caught);
    }
  }

  if (settings.blocked) return <SettingsBlocked />;

  return (
    <>
      <Step number={1} title="Upload OpenFloat's statement" />
      <FileDrop
        label="Transaction Statement file(s) downloaded from OpenFloat"
        hint="You can pick several at once if the disbursement was split."
        accept=".xlsx,.xls,.xlsm"
        multiple
        files={statements}
        onFiles={(files) => {
          if (withinLimit(files)) setStatements(files);
        }}
      />

      <Step number={2} title="Add your original file" optional />
      <FileDrop
        label="The Process Maker export you prepared the upload from"
        hint="Add it to find people who were on your list but never paid."
        accept=".csv,.xlsx,.xls,.xlsm"
        files={input ? [input] : []}
        onFiles={(files) => {
          const picked = files[0] ?? null;
          if (picked && withinLimit([picked])) setInput(picked);
        }}
      />
      {input && (
        <button type="button" className="button button-small" onClick={() => setInput(null)}>
          Remove {input.name}
        </button>
      )}

      {tooBig && (
        <Notice tone="error">
          '{tooBig}' is larger than 20 MB. A real statement is a few hundred KB. Is it the right file?
        </Notice>
      )}

      {statements.length === 0 ? (
        <Notice tone="info">Upload at least one Transaction Statement to see the results.</Notice>
      ) : error !== null ? (
        <ReportError error={error} hasInput={input !== null} />
      ) : report === null ? (
        <p className="muted" role="status">Building report…</p>
      ) : (
        <Results
          report={report}
          onDownload={download}
          downloadError={downloadError}
        />
      )}
    </>
  );
}

function ReportError({ error, hasInput }: { error: unknown; hasInput: boolean }) {
  // The statements themselves never fail the request (a bad one lands in the
  // report's own errors), so a 400 here is the Process Maker file.
  if (hasInput && error instanceof ApiError && error.status === 400) {
    return (
      <ErrorNotice
        message="We couldn't open your Process Maker file. Check it is a CSV or Excel file and isn't open in Excel, or remove it to see the statement results on their own."
        error={error}
      />
    );
  }
  return (
    <ErrorNotice
      message="Something went wrong while reading the statement(s). Check they are the Transaction Statement files from OpenFloat and try again."
      error={error}
    />
  );
}

function Results({ report, onDownload, downloadError }: {
  report: StatementReport;
  onDownload: (kind: StatementWorkbook, fallback: string) => void;
  downloadError: unknown;
}) {
  const errors = report.errors ?? [];
  const transactions = report.transactions ?? [];
  const unsuccessful = report.unsuccessful_transactions ?? [];
  const combined = report.combined;

  return (
    <>
      {errors.length > 0 && (
        <Notice tone="error">
          <p>Some files could not be read, so they are <strong>not</strong> included in the results below:</p>
          <ul>
            {errors.map((message) => <li key={message}>{message}</li>)}
          </ul>
        </Notice>
      )}

      {transactions.length === 0 || !combined ? (
        <Notice tone="warning">
          No transactions were found. Check you uploaded OpenFloat's Transaction Statement, not the
          upload file or one of this app's reports.
        </Notice>
      ) : (
        <>
          <Step number={3} title="Results" />
          <MetricRow>
            <Metric label="Transactions" value={combined.total_rows ?? 0} />
            <Metric label="Successful" value={combined.successful_count ?? 0} />
            <Metric label="Unsuccessful" value={combined.unsuccessful_count ?? 0} />
            <Metric label="Paid out (KES)" value={kes(combined.total_disbursed ?? 0)} />
          </MetricRow>
          {(combined.unsuccessful_count ?? 0) > 0 && (
            <Notice tone="warning">
              <strong>{combined.unsuccessful_count}</strong> payment(s) did NOT go through. These
              people may need to be paid again. They are listed below.
            </Notice>
          )}

          {/* First, because it's the one thing on this page someone has to act on. */}
          {unsuccessful.length > 0 ? (
            <details className="panel panel-error" open>
              <summary>Payments that did not go through ({unsuccessful.length})</summary>
              <DataTable
                caption="Payments that did not go through"
                columns={TRANSACTION_COLUMNS}
                rows={transactionRows(unsuccessful)}
              />
            </details>
          ) : (
            <Notice tone="success">Every payment in every statement went through.</Notice>
          )}

          <Step number={4} title="Download the reports" />
          <div className="download-grid">
            <div>
              <button
                type="button"
                className="button button-primary button-block"
                onClick={() => onDownload("report", "statement_report.xlsx")}
              >
                Statement Report (Excel)
              </button>
              <p className="field-help">
                For project leads: Successful and Unsuccessful
                {report.reconciliation ? ", plus the four reconciliation sheets" : ""}. Each sheet
                is totalled at the bottom.
              </p>
            </div>
            <div>
              <button
                type="button"
                className="button button-primary button-block"
                onClick={() => onDownload("finance", "finance_reconciliation.xlsx")}
              >
                Finance Reconciliation (Excel)
              </button>
              <p className="field-help">
                Debit totals successful payments only; unsuccessful rows are shaded and excluded.
              </p>
            </div>
          </div>
          {downloadError !== null && (
            <ErrorNotice
              message="Something went wrong while building the report. Nothing was downloaded. Try again, and if it keeps happening, ask for help."
              error={downloadError}
            />
          )}

          <h3 className="subheading">More detail</h3>
          <FileSummaries report={report} />
          <StatusCounts report={report} />
          <CaseRollups report={report} />
          <Reconciliation report={report} />
          {(report.warnings ?? []).length > 0 && (
            <details className="panel panel-warning">
              <summary>Rows we could not fully read ({report.warnings?.length})</summary>
              <DataTable
                caption="Rows we could not fully read"
                columns={["Warning"]}
                rows={(report.warnings ?? []).map((warning) => [warning])}
              />
            </details>
          )}
        </>
      )}
    </>
  );
}

function FileSummaries({ report }: { report: StatementReport }) {
  const summaries = report.file_summaries ?? [];
  if (summaries.length === 0) return null;
  return (
    <>
      {/* Worth opening by default only when there are several files to compare. */}
      <details className="panel" open={summaries.length > 1}>
        <summary>Each file</summary>
        <DataTable
          caption="Each file"
          columns={["File", "Rows", "Successful", "Unsuccessful", "Paid out (KES)", "OpenFloat's own total", "Totals agree"]}
          rows={summaries.map((s) => [
            s.file_name ?? "",
            String(s.total_rows ?? 0),
            String(s.successful_count ?? 0),
            String(s.unsuccessful_count ?? 0),
            kes(s.total_disbursed ?? 0),
            kes(s.footer_total),
            s.footer_matches === null || s.footer_matches === undefined ? "—" : s.footer_matches ? "Yes" : "No",
          ])}
        />
      </details>
      {/* Outside the panel: a total that disagrees must not hide in a closed panel. */}
      {summaries
        .filter((s) => s.footer_matches === false)
        .map((s) => (
          <Notice key={s.file_name} tone="warning">
            <strong>{s.file_name}</strong>: OpenFloat's own total at the bottom of the file (
            {kes(s.footer_total)}) does not match the successful payments we counted (
            {kes(s.total_disbursed)}). Check the file before relying on these figures.
          </Notice>
        ))}
    </>
  );
}

function StatusCounts({ report }: { report: StatementReport }) {
  const counts = Object.entries(report.combined?.counts_by_status ?? {});
  if (counts.length <= 1 && (report.combined?.unsuccessful_count ?? 0) === 0) return null;
  return (
    <details className="panel">
      <summary>Count by status</summary>
      <DataTable
        caption="Count by status"
        columns={["Status", "Count"]}
        rows={counts.sort(([, a], [, b]) => b - a).map(([status, count]) => [status, String(count)])}
      />
    </details>
  );
}

function CaseRollups({ report }: { report: StatementReport }) {
  const rollups = report.case_rollups ?? [];
  return (
    <>
      <details className="panel">
        <summary>Totals per case</summary>
        {rollups.length > 0 ? (
          <DataTable
            caption="Totals per case"
            columns={["Case #", "Project", "Activity", "Amount in reference", "Rows", "Successful", "Unsuccessful", "Paid out", "Difference"]}
            rows={rollups.map((r) => [
              r.case_number,
              r.project_code || "—",
              r.activity_code || "—",
              kes(r.remark_amount),
              String(r.total_rows),
              String(r.successful_count),
              String(r.unsuccessful_count ?? 0),
              kes(r.disbursed_total ?? 0),
              kes(r.difference),
            ])}
          />
        ) : (
          <Notice tone="info">No case references (C#...) could be read from the Remark column.</Notice>
        )}
      </details>
      {/* Outside the panel: a case paid more or less than its reference is a
          finding, not a detail. null (a short reference, nothing to compare)
          and 0 both mean nothing to flag. */}
      {rollups
        .filter((r) => r.difference)
        .map((r) => (
          <Notice key={r.case_number} tone="warning">
            <strong>Case #{r.case_number}</strong>: the case reference says KES {kes(r.remark_amount)},
            but KES {kes(r.disbursed_total)} was actually paid out (difference {kes(r.difference)}).
          </Notice>
        ))}
    </>
  );
}

function Reconciliation({ report }: { report: StatementReport }) {
  const rec = report.reconciliation;
  if (!rec) return null;
  const buckets: Array<[string, ReconciliationEntry[]]> = [
    ["Paid", rec.matched_paid ?? []],
    ["On the statement, not paid", rec.matched_not_paid ?? []],
    ["In your file, not on the statement", rec.missing_from_statement ?? []],
    ["On the statement, not in your file", rec.statement_not_in_input ?? []],
  ];
  const missing = rec.missing_from_statement ?? [];
  const duplicates = rec.duplicate_input_phones ?? [];
  const multiplyPaid = rec.multiply_paid_phones ?? [];

  return (
    <>
      <h3 className="subheading">Compared with your Process Maker file</h3>
      <MetricRow>
        {buckets.map(([label, entries]) => (
          <Metric key={label} label={label} value={entries.length} />
        ))}
      </MetricRow>
      {missing.length > 0 && (
        <Notice tone="warning">
          <strong>{missing.length}</strong> phone number(s) in your file are not on any statement you
          uploaded, so there is no record of them being paid. Were their rows left out of the
          upload, or is a statement file missing?
        </Notice>
      )}
      {buckets
        .filter(([, entries]) => entries.length > 0)
        .map(([label, entries]) => (
          <details key={label} className="panel">
            <summary>{label} ({entries.length})</summary>
            <DataTable caption={label} columns={ENTRY_COLUMNS} rows={entryRows(entries, label)} />
          </details>
        ))}
      {duplicates.length > 0 && (
        <Notice tone="warning">
          The same phone number appears more than once in your file: {duplicates.join(", ")}
        </Notice>
      )}
      {multiplyPaid.length > 0 && (
        <Notice tone="warning">These phone numbers were paid more than once: {multiplyPaid.join(", ")}</Notice>
      )}
    </>
  );
}
