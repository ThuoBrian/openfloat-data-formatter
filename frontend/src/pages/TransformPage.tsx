/**
 * "Prepare an OpenFloat upload": upload → check columns → fix problems →
 * download, as four numbered steps. Mirrors ui/app.py::render_transform_page.
 *
 * The file stays in the browser and is posted again whenever a choice
 * changes. The API keeps nothing between requests, so no upload outlives the
 * request that read it.
 */
import { useEffect, useState } from "react";

import {
  ApiError,
  MAX_UPLOAD_BYTES,
  downloadWorkbook,
  previewUpload,
  uploadForm,
  type UploadCheck,
  type UploadChoices,
  type UploadPreview,
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
import { ISSUE_COLUMNS, MAPPABLE_FIELDS, issueRows } from "./labels";

/** How long typing in the Project code box waits before asking the API again. */
const PREVIEW_DELAY_MS = 300;

const NOT_PRESENT = "";
const AUTO_DETECT = "";

export interface TransformSettings {
  /** A sidebar setting is invalid: keep everything, but don't run until it's fixed. */
  blocked: boolean;
  countryPrefix: string;
  maxAmountThreshold: number;
  /** ACCOUNT_NAME_COLUMN and PROJECT_CODE from .env: where the controls start. */
  defaultAccountNameColumn: string | null;
  defaultProjectCode: string | null;
}

export function TransformPage({ settings }: { settings: TransformSettings }) {
  const [file, setFile] = useState<File | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  // undefined = untouched: start from .env's ACCOUNT_NAME_COLUMN.
  const [identifier, setIdentifier] = useState<string | null | undefined>(undefined);
  const [projectCode, setProjectCode] = useState(settings.defaultProjectCode ?? "");
  const [check, setCheck] = useState<UploadCheck | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<unknown>(null);

  const choices: UploadChoices = {
    columnOverrides: overrides,
    accountNameColumn: identifier === undefined ? settings.defaultAccountNameColumn : identifier,
    projectCode,
    countryPrefix: settings.countryPrefix,
    maxAmountThreshold: settings.maxAmountThreshold,
  };
  const choicesKey = JSON.stringify(choices);

  useEffect(() => {
    if (!file || settings.blocked) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setBusy(true);
      previewUpload(uploadForm(file, JSON.parse(choicesKey) as UploadChoices), controller.signal)
        .then((result) => {
          setCheck(result);
          setError(null);
        })
        .catch((caught: unknown) => {
          if (controller.signal.aborted) return;
          setCheck(null);
          setError(caught);
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [file, choicesKey, settings.blocked]);

  function pickFile(files: File[]) {
    const picked = files[0];
    if (!picked) return;
    // A different file has different columns, so earlier picks no longer apply.
    setOverrides({});
    setIdentifier(undefined);
    setCheck(null);
    setDownloadError(null);
    if (picked.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setError(new ApiError(413, `'${picked.name}' is larger than 20 MB.`));
      return;
    }
    setError(null);
    setFile(picked);
  }

  async function download(path: string, fallback: string) {
    if (!file) return;
    setDownloadError(null);
    try {
      await downloadWorkbook(path, uploadForm(file, choices), fallback);
    } catch (caught) {
      setDownloadError(caught);
    }
  }

  const stem = file ? file.name.replace(/\.[^.]+$/, "") : "upload";

  if (settings.blocked) return <SettingsBlocked />;

  return (
    <>
      <Step number={1} title="Upload your file" />
      <FileDrop
        label="Your Process Maker airtime export (CSV or Excel)"
        hint="Drag the file here, or click to pick it."
        accept=".csv,.xlsx,.xls,.xlsm"
        onFiles={pickFile}
        files={file ? [file] : []}
      />

      {!file && !error && (
        <Notice tone="info">
          Upload a file to get started. Filling one in by hand? Use{" "}
          <code>docs/processmaker-input-template.xlsx</code> in the app's folder. It has the
          right columns already.
        </Notice>
      )}
      {error !== null && <FileError error={error} />}
      {file && !check && !error && <p className="muted" role="status">Reading your file…</p>}

      {check && check.preview.row_count === 0 && (
        <Notice tone="warning">This file has column headers but no rows. Is it the right file?</Notice>
      )}

      {check && check.preview.row_count > 0 && (
        <div aria-busy={busy}>
          <Step number={2} title="Check the columns" />
          <ColumnMapping
            preview={check.preview}
            overrides={overrides}
            identifierChoice={identifier}
            onOverride={(field, column) =>
              setOverrides((current) => {
                const next = { ...current };
                if (column === NOT_PRESENT) delete next[field];
                else next[field] = column;
                return next;
              })
            }
            onIdentifier={(column) => setIdentifier(column === AUTO_DETECT ? null : column)}
          />
          <p className="muted">
            Your file has <strong>{check.preview.row_count} rows</strong>. The first{" "}
            {Math.min(check.preview.row_count, check.preview.preview_rows.length)} are shown below
            so you can check it is the right file.
          </p>
          <DataTable
            caption="First rows of your file"
            columns={check.preview.preview_columns}
            rows={check.preview.preview_rows}
          />
          <ProjectCode preview={check.preview} value={projectCode} onChange={setProjectCode} />
          {check.preview.remark_preview && (
            <p className="muted">
              Remark preview (row 1): <code>{check.preview.remark_preview}</code>
              {!check.preview.remark_readable &&
                " (not a case reference the statement report can read)"}
            </p>
          )}

          <Problems check={check} onDownloadRejected={() => download("/rejected-rows", `${stem}_rows_to_fix.xlsx`)} />

          <Step number={4} title="Download your upload file" />
          <DownloadStep
            check={check}
            onDownload={() => download("/transform", `${stem}_openfloat.xlsx`)}
          />
          {downloadError !== null && (
            <ErrorNotice
              message="Something went wrong while building the file. Nothing was downloaded. Try again, and if it keeps happening, ask for help."
              error={downloadError}
            />
          )}
        </div>
      )}
    </>
  );
}

function FileError({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.status === 413) {
    return <Notice tone="error">{error.message} A real export is a few hundred KB. Is it the right file?</Notice>;
  }
  if (error instanceof ApiError && error.status === 400) {
    return (
      <ErrorNotice
        message="We couldn't open this file. Check it is the Process Maker export (CSV or Excel), that it isn't open in Excel right now, and try again."
        error={error}
      />
    );
  }
  return (
    <ErrorNotice
      message="Something went wrong while preparing your file. Try again, and if it keeps happening, ask for help."
      error={error}
    />
  );
}

/**
 * Every column choice in one place: they're the same decision from the user's
 * side ("which of my columns is this?"). Detection pre-selects each, so a
 * recognised file needs no interaction and this stays closed. It opens by
 * itself when something is missing.
 */
function ColumnMapping({ preview, overrides, identifierChoice, onOverride, onIdentifier }: {
  preview: UploadPreview;
  overrides: Record<string, string>;
  identifierChoice: string | null | undefined;
  onOverride: (field: string, column: string) => void;
  onIdentifier: (column: string) => void;
}) {
  const missing = [
    ...MAPPABLE_FIELDS.filter(([field]) => preview.missing_fields.includes(field)).map(([, label]) => label),
    ...(preview.identifier_column === null ? ["Identifier"] : []),
  ];
  const identifierValue =
    identifierChoice === null ? AUTO_DETECT : (identifierChoice ?? preview.identifier_column ?? AUTO_DETECT);

  return (
    <>
      <details className="panel" open={missing.length > 0}>
        <summary>
          Column mapping{missing.length > 0 && ` (${missing.length} not found)`}
        </summary>
        <p className="muted">
          Your export can name these columns anything. We guess from the header; correct any that
          are wrong.
        </p>
        <div className="field-grid">
          {MAPPABLE_FIELDS.map(([field, label]) => {
            const current = overrides[field] ?? preview.mapping[field] ?? NOT_PRESENT;
            const found = current !== NOT_PRESENT && preview.columns.includes(current);
            return (
              <div key={field} className="field">
                <label className="field-control">
                  <span className="field-label">{label}</span>
                  <select value={found ? current : NOT_PRESENT} onChange={(event) => onOverride(field, event.target.value)}>
                    {/* Offered only when there's genuinely nothing to point at. */}
                    {!found && <option value={NOT_PRESENT}>(not in this file)</option>}
                    {preview.columns.map((column) => (
                      <option key={column} value={column}>{column}</option>
                    ))}
                  </select>
                </label>
              </div>
            );
          })}
          <div className="field">
            <label className="field-control">
              <span className="field-label">Identifier (Account Name)</span>
              <select
                value={identifierValue}
                onChange={(event) => onIdentifier(event.target.value)}
                aria-describedby="identifier-help"
              >
                <option value={AUTO_DETECT}>(auto-detect)</option>
                {preview.columns.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
            <span className="field-help" id="identifier-help">
              Staff ID, Respondent ID, Case ID: whatever this export calls it. Written to the
              output Account Name so a payment can be traced back to its source record.
            </span>
          </div>
        </div>
        {preview.identifier_column !== null ? (
          <p className="muted">
            Account Name will use <strong>{preview.identifier_column}</strong>:{" "}
            {preview.identifier_filled}/{preview.row_count} rows have a value
            {preview.identifier_samples.length > 0 && ` (e.g. ${preview.identifier_samples.join(", ")})`}
          </p>
        ) : (
          <p className="text-warning">
            No identifier column detected. Account Name will be blank for every row unless you
            pick one.
          </p>
        )}
        {preview.mapping_warnings.map((warning) => (
          <p key={warning} className="text-warning">{warning}</p>
        ))}
      </details>
      {preview.missing_fields.length > 0 && (
        <Notice tone="error">
          No column chosen for:{" "}
          <strong>
            {MAPPABLE_FIELDS.filter(([field]) => preview.missing_fields.includes(field))
              .map(([, label]) => label)
              .join(", ")}
          </strong>
          . Every row will fail until you pick one under <strong>Column mapping</strong>.
        </Notice>
      )}
    </>
  );
}

/**
 * The project code completes a short `C# 38305` case reference into the full
 * Remark. A project-code column in the file wins row by row; this is the
 * fallback, so the box only appears when it could matter.
 */
function ProjectCode({ preview, value, onChange }: {
  preview: UploadPreview;
  value: string;
  onChange: (value: string) => void;
}) {
  if (!preview.short_form_rows && preview.project_code_column === null) return null;
  const typed = value.trim();
  return (
    <div className="panel">
      <div className="field">
        <label className="field-control">
          <span className="field-label">Project code for the case reference</span>
          <input
            type="text"
            value={value}
            placeholder="e.g. 22505AA"
            onChange={(event) => onChange(event.target.value)}
            aria-describedby="project-code-help"
          />
        </label>
        <span className="field-help" id="project-code-help">
          Used to complete a short "C# 38305" reference into the full Remark. A project_code
          column in the file takes precedence, row by row.
        </span>
      </div>
      {preview.project_code_column !== null && (
        <p className="muted">
          This file has a <strong>{preview.project_code_column}</strong> column. It is used per
          row, and this box only fills rows where it is blank.
        </p>
      )}
      {typed.includes(" ") ? (
        <Notice tone="warning">
          A project code cannot contain spaces. The case reference would not be readable, so those
          rows would keep a short Remark.
        </Notice>
      ) : (
        preview.short_form_rows > 0 &&
        !typed &&
        preview.project_code_column === null && (
          <Notice tone="warning">
            {preview.short_form_rows} row(s) carry a short case reference. Without a project code
            their Remark stays short (e.g. <code>C#38305</code>).
          </Notice>
        )
      )}
    </div>
  );
}

function Problems({ check, onDownloadRejected }: { check: UploadCheck; onDownloadRejected: () => void }) {
  const report = check.report;
  const errors = report.errors ?? [];
  const warnings = report.warnings ?? [];
  const counts = report.filtered_counts;
  const leftOut = report.total_rows - report.valid_rows;

  return (
    <>
      <Step number={3} title="Fix any problems" />
      <MetricRow>
        <Metric label="Rows in your file" value={report.total_rows} />
        <Metric label="Ready for OpenFloat" value={report.valid_rows} />
        <Metric label="Left out" value={leftOut} />
      </MetricRow>

      {errors.length > 0 && (
        <details className="panel panel-error" open>
          <summary>Rows that will be left out ({errors.length})</summary>
          <p className="muted">
            Row numbers match the rows in your own spreadsheet. Fix these at the source, then upload
            the corrected file here again.
          </p>
          <DataTable caption="Rows that will be left out" columns={ISSUE_COLUMNS} rows={issueRows(errors)} />
          <button type="button" className="button" onClick={onDownloadRejected}>
            Download the rows that need fixing
          </button>
          <p className="field-help">
            Send this to whoever compiled the file. It has their own columns plus the reason each
            row was left out.
          </p>
        </details>
      )}

      {counts && (counts.invalid_phone > 0 || counts.invalid_amount > 0 || counts.unmapped_network > 0) && (
        <details className="panel">
          <summary>Why rows were left out</summary>
          <ul>
            {counts.invalid_phone > 0 && <li>Invalid phone number: <strong>{counts.invalid_phone}</strong></li>}
            {counts.invalid_amount > 0 && <li>Invalid amount: <strong>{counts.invalid_amount}</strong></li>}
            {counts.unmapped_network > 0 && <li>Unrecognised network: <strong>{counts.unmapped_network}</strong></li>}
          </ul>
        </details>
      )}

      {warnings.length > 0 && (
        <details className="panel panel-warning">
          <summary>Worth checking ({warnings.length})</summary>
          <p className="muted">
            These rows <strong>are</strong> in the upload file. Nothing is wrong for certain, but
            take a look (e.g. a very large amount, or the same phone number twice).
          </p>
          <DataTable caption="Rows worth checking" columns={ISSUE_COLUMNS} rows={issueRows(warnings)} />
        </details>
      )}

      {errors.length === 0 && warnings.length === 0 && (
        <Notice tone="success">Every row in this file can be uploaded.</Notice>
      )}
    </>
  );
}

function DownloadStep({ check, onDownload }: { check: UploadCheck; onDownload: () => void }) {
  const leftOut = check.report.total_rows - check.report.valid_rows;
  if (check.output_row_count === 0) {
    return (
      <Notice tone="error">
        There is nothing to download: every row was left out. Fix the rows above and upload the
        file again.
      </Notice>
    );
  }
  return (
    <>
      {/* The easiest mistake here is uploading a partial file believing it is
          complete, so say so right beside the button. */}
      {leftOut > 0 && (
        <Notice tone="warning">
          This file is <strong>missing {leftOut} row(s)</strong> that had problems (see Step 3).
          Those people will not be paid unless their rows are fixed and sent separately.
        </Notice>
      )}
      <button type="button" className="button button-primary" onClick={onDownload}>
        Download {check.output_row_count} rows for OpenFloat
      </button>
      <p className="muted">
        Next: upload this file to OpenFloat. When the disbursement finishes, download its
        Transaction Statement and come back to <strong>Check payment results</strong> to see what
        went through.
      </p>
    </>
  );
}
