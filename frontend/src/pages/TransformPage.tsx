/**
 * "Prepare an OpenFloat upload": upload → check columns → fix problems →
 * download, as four numbered steps.
 *
 * Layout: steps 1-3 run down the page; step 4 (the figures and the Download
 * button) sits in a summary panel beside them that stays in view, so the
 * outcome is never a long scroll away. On a narrow window it drops below.
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
import { DataTable, ErrorNotice, FileDrop, Notice, SettingsBlocked, Stats, Step } from "../components/ui";
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
  const ready = check !== null && check.preview.row_count > 0;

  if (settings.blocked) return <SettingsBlocked />;

  return (
    <div className={ready ? "page page-with-rail" : "page"}>
      <div className="page-main" aria-busy={busy}>
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

        {ready && (
          <>
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
            <ProjectCode preview={check.preview} value={projectCode} onChange={setProjectCode} />
            <details className="panel">
              <summary>
                Preview the first {check.preview.preview_rows.length} of{" "}
                {check.preview.row_count} rows
              </summary>
              <DataTable
                caption="First rows of your file"
                columns={check.preview.preview_columns}
                rows={check.preview.preview_rows}
              />
            </details>

            <Problems
              check={check}
              onDownloadRejected={() => download("/rejected-rows", `${stem}_rows_to_fix.xlsx`)}
            />
          </>
        )}
      </div>

      {ready && (
        <aside className="page-rail" aria-label="Your upload file">
          <DownloadCard
            check={check}
            onDownload={() => download("/transform", `${stem}_openfloat.xlsx`)}
            downloadError={downloadError}
          />
        </aside>
      )}
    </div>
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
 * Which column each field is read from, as a summary rather than a form: a
 * recognised file needs no interaction, so the dropdowns stay out of the way
 * until "Change" is clicked. They open by themselves when something is missing.
 */
function ColumnMapping({ preview, overrides, identifierChoice, onOverride, onIdentifier }: {
  preview: UploadPreview;
  overrides: Record<string, string>;
  identifierChoice: string | null | undefined;
  onOverride: (field: string, column: string) => void;
  onIdentifier: (column: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const missingLabels = MAPPABLE_FIELDS.filter(([field]) => preview.missing_fields.includes(field)).map(
    ([, label]) => label,
  );
  const mustPick = missingLabels.length > 0;
  const open = editing || mustPick;
  const identifierValue =
    identifierChoice === null ? AUTO_DETECT : (identifierChoice ?? preview.identifier_column ?? AUTO_DETECT);

  return (
    <>
      <section className="panel" aria-labelledby="columns-heading">
        <div className="panel-head">
          <h3 id="columns-heading" className="panel-title">
            {mustPick ? `Columns: ${missingLabels.length} not found` : "Columns we'll read"}
          </h3>
          {!mustPick && (
            <button
              type="button"
              className="button button-small"
              aria-expanded={open}
              onClick={() => setEditing((value) => !value)}
            >
              {open ? "Done" : "Change"}
            </button>
          )}
        </div>

        <dl className="mapping">
          {MAPPABLE_FIELDS.map(([field, label]) => (
            <div key={field}>
              <dt>{label}</dt>
              <dd>
                {preview.mapping[field] ?? <span className="text-danger">Not found</span>}
              </dd>
            </div>
          ))}
          <div>
            <dt>Account Name</dt>
            <dd>
              {preview.identifier_column ?? <span className="text-warning">None, will be blank</span>}
              {preview.identifier_column !== null && (
                <span className="mapping-note">
                  {preview.identifier_filled} of {preview.row_count} rows filled
                  {preview.identifier_samples.length > 0 &&
                    `, e.g. ${preview.identifier_samples.join(", ")}`}
                </span>
              )}
            </dd>
          </div>
          {preview.remark_preview && (
            <div className="mapping-wide">
              <dt>Remark (row 1)</dt>
              <dd>
                <code>{preview.remark_preview}</code>
                {!preview.remark_readable && (
                  <span className="mapping-note text-warning">
                    Not a case reference the payment results page can read.
                  </span>
                )}
              </dd>
            </div>
          )}
        </dl>

        {open && (
          <div className="field-grid mapping-edit">
            {MAPPABLE_FIELDS.map(([field, label]) => {
              const current = overrides[field] ?? preview.mapping[field] ?? NOT_PRESENT;
              const found = current !== NOT_PRESENT && preview.columns.includes(current);
              return (
                <div key={field} className="field">
                  <label className="field-control">
                    <span className="field-label">{label}</span>
                    <select
                      value={found ? current : NOT_PRESENT}
                      onChange={(event) => onOverride(field, event.target.value)}
                    >
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
                <span className="field-label">Account Name (ID column)</span>
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
                Staff ID, Respondent ID, Case ID: whatever this export calls it, so a payment can
                be traced back to its record.
              </span>
            </div>
          </div>
        )}

        {preview.mapping_warnings.map((warning) => (
          <p key={warning} className="text-warning panel-note">{warning}</p>
        ))}
      </section>
      {mustPick && (
        <Notice tone="error">
          No column chosen for: <strong>{missingLabels.join(", ")}</strong>. Every row will fail
          until you pick one above.
        </Notice>
      )}
    </>
  );
}

/**
 * The project code completes a short `C# 38305` case reference into the full
 * Remark, so it only appears when the file has short references to complete.
 * A project-code column in the file wins row by row; this is the fallback.
 */
function ProjectCode({ preview, value, onChange }: {
  preview: UploadPreview;
  value: string;
  onChange: (value: string) => void;
}) {
  if (!preview.short_form_rows) return null;
  const typed = value.trim();
  return (
    <section className="panel" aria-labelledby="project-code-heading">
      <h3 id="project-code-heading" className="panel-title">
        {preview.short_form_rows} row(s) have a short case reference
      </h3>
      <div className="field field-inline">
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
          {preview.project_code_column !== null
            ? `Fills the rows where the file's ${preview.project_code_column} column is blank.`
            : `Completes "C# 38305" into the full reference, e.g. C#38305 22505AA RESP AIRTIME-KSH28000 g06.`}
        </span>
      </div>
      {typed.includes(" ") ? (
        <Notice tone="warning">
          A project code cannot contain spaces. The case reference would not be readable, so those
          rows would keep a short Remark.
        </Notice>
      ) : (
        !typed &&
        preview.project_code_column === null && (
          <Notice tone="warning">
            {preview.short_form_rows} row(s) carry a short case reference. Without a project code
            their Remark stays short (e.g. <code>C#38305</code>).
          </Notice>
        )
      )}
    </section>
  );
}

function Problems({ check, onDownloadRejected }: { check: UploadCheck; onDownloadRejected: () => void }) {
  const report = check.report;
  const errors = report.errors ?? [];
  const warnings = report.warnings ?? [];
  const counts = report.filtered_counts;
  const reasons = [
    counts?.invalid_phone ? `${counts.invalid_phone} invalid phone number` : null,
    counts?.invalid_amount ? `${counts.invalid_amount} invalid amount` : null,
    counts?.unmapped_network ? `${counts.unmapped_network} unrecognised network` : null,
  ].filter((reason): reason is string => reason !== null);

  return (
    <>
      <Step number={3} title="Fix any problems" />

      {errors.length > 0 && (
        <details className="panel panel-error" open>
          <summary>Rows that will be left out ({errors.length})</summary>
          {reasons.length > 0 && <p className="panel-note">{reasons.join(", ")}.</p>}
          <p className="muted">
            Row numbers match the rows in your own spreadsheet. Fix these at the source, then upload
            the corrected file here again.
          </p>
          <DataTable caption="Rows that will be left out" columns={ISSUE_COLUMNS} rows={issueRows(errors)} />
          <div className="panel-actions">
            <button type="button" className="button" onClick={onDownloadRejected}>
              Download the rows that need fixing
            </button>
            <span className="field-help">
              Their own columns plus the reason, to send to whoever compiled the file.
            </span>
          </div>
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

/** Step 4, in the summary panel: the figures, then the one thing to do next. */
function DownloadCard({ check, onDownload, downloadError }: {
  check: UploadCheck;
  onDownload: () => void;
  downloadError: unknown;
}) {
  const report = check.report;
  const leftOut = report.total_rows - report.valid_rows;
  return (
    <section className="rail-card">
      <Step number={4} title="Download your upload file" />
      <Stats
        items={[
          ["Rows in your file", report.total_rows],
          ["Ready for OpenFloat", report.valid_rows],
          ["Left out", <span className={leftOut > 0 ? "text-danger" : undefined}>{leftOut}</span>],
        ]}
      />
      {check.output_row_count === 0 ? (
        <Notice tone="error">
          There is nothing to download: every row was left out. Fix the rows and upload the file
          again.
        </Notice>
      ) : (
        <>
          {/* The easiest mistake here is uploading a partial file believing it
              is complete, so say so right beside the button. */}
          {leftOut > 0 && (
            <Notice tone="warning">
              This file is <strong>missing {leftOut} row(s)</strong> that had problems (see Step
              3). Those people will not be paid unless their rows are fixed and sent separately.
            </Notice>
          )}
          <button type="button" className="button button-primary button-block" onClick={onDownload}>
            Download {check.output_row_count} rows for OpenFloat
          </button>
          <p className="rail-note">
            Next: upload this file to OpenFloat. When the disbursement finishes, come back to{" "}
            <strong>Check payment results</strong> with its Transaction Statement.
          </p>
        </>
      )}
      {downloadError !== null && (
        <ErrorNotice
          message="Something went wrong while building the file. Nothing was downloaded. Try again, and if it keeps happening, ask for help."
          error={downloadError}
        />
      )}
    </section>
  );
}
