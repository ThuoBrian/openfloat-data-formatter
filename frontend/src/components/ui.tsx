/** Small building blocks shared by both pages. Styling lives in app.css. */
import { useId, useState, type ReactNode } from "react";

/** A numbered step heading: the page's main way of saying "you are here". */
export function Step({ number, title, optional = false }: {
  number: number;
  title: string;
  optional?: boolean;
}) {
  return (
    <h2 className="step">
      <span className="step-number" aria-hidden="true">{number}</span>
      <span>
        <span className="visually-hidden">Step {number}: </span>
        {title}
        {optional && <span className="step-optional"> (optional)</span>}
      </span>
    </h2>
  );
}

export type Tone = "error" | "warning" | "success" | "info";

/** A coloured message. Errors and warnings are announced to screen readers. */
export function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  const role = tone === "error" || tone === "warning" ? "alert" : "status";
  return (
    <div className={`notice notice-${tone}`} role={role}>
      {children}
    </div>
  );
}

/**
 * A plain-English error with the technical text tucked away. The raw message
 * means nothing to the staff using this, but it's exactly what whoever
 * supports them needs.
 */
export function ErrorNotice({ message, error }: { message: string; error: unknown }) {
  const detail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  return (
    <Notice tone="error">
      <p>{message}</p>
      <details className="technical">
        <summary>Technical details (include these if you ask for help)</summary>
        <pre>{detail}</pre>
      </details>
    </Notice>
  );
}

/** Shown in place of a page while a sidebar setting is invalid. */
export function SettingsBlocked() {
  return (
    <Notice tone="error">
      Fix the setting under <strong>Advanced settings</strong> to continue.
    </Notice>
  );
}

export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

export function MetricRow({ children }: { children: ReactNode }) {
  return <div className="metric-row">{children}</div>;
}

/** A scrollable table. Cells are text; React escapes them. */
export function DataTable({ columns, rows, caption }: {
  columns: string[];
  rows: ReactNode[][];
  caption: string;
}) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th key={index} scope="col">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A drop zone that is also a normal, keyboard-reachable file input. */
export function FileDrop({ label, hint, accept, multiple = false, onFiles, files }: {
  label: string;
  hint: string;
  accept: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  files: File[];
}) {
  const id = useId();
  const [dragging, setDragging] = useState(false);

  return (
    <div
      className={`drop${dragging ? " drop-active" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const dropped = Array.from(event.dataTransfer.files);
        if (dropped.length > 0) onFiles(multiple ? dropped : dropped.slice(0, 1));
      }}
    >
      <label htmlFor={id} className="drop-label">{label}</label>
      <p className="drop-hint">{hint}</p>
      <input
        id={id}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []));
          // Let the same file be picked again after "Start over".
          event.target.value = "";
        }}
      />
      {files.length > 0 && (
        <ul className="drop-files">
          {files.map((file) => (
            <li key={`${file.name}-${file.size}`}>
              {file.name} <span className="muted">({formatSize(file.size)})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
