/**
 * The only code that talks to the local API. Everything goes to the same
 * origin the page was served from (127.0.0.1), so nothing leaves the computer.
 *
 * Types come from `schema.ts`, generated from docs/openapi.json
 * (`npm run gen:api`). Don't hand-edit them: change the Python models and
 * regenerate, so the page and the API can't disagree.
 */
import type { components } from "./schema";

export type UploadCheck = components["schemas"]["UploadCheck"];
export type UploadPreview = components["schemas"]["UploadPreview"];
export type ValidationReport = components["schemas"]["ValidationReport"];
export type ValidationIssue = components["schemas"]["ValidationIssue"];
export type UiDefaults = components["schemas"]["UiDefaults"];
export type StatementReport = components["schemas"]["StatementReport"];
export type StatementTransaction = components["schemas"]["StatementTransaction"];
export type StatementFileSummary = components["schemas"]["StatementFileSummary"];
export type CaseRollup = components["schemas"]["CaseRollup"];
export type ReconciliationEntry = components["schemas"]["ReconciliationEntry"];
/** Which statement download: the project leads' report or the finance sheet. */
export type StatementWorkbook = "report" | "finance";

/** Every POST must carry this, or the API refuses it (see main.py). */
export const CLIENT_HEADER = { "X-OpenFloat-Client": "1" } as const;

/** Same ceiling the API enforces (main.py MAX_UPLOAD_BYTES), checked before sending. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/** A request the API answered with an error status. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The choices that shape how one Process Maker file is read. */
export interface UploadChoices {
  /** Canonical field → the column the user picked. Only fields they changed. */
  columnOverrides: Record<string, string>;
  /** Column feeding Account Name; null = let the API detect it. */
  accountNameColumn: string | null;
  projectCode: string;
  countryPrefix: string;
  maxAmountThreshold: number;
}

export function uploadForm(file: File, choices: UploadChoices): FormData {
  const form = new FormData();
  form.append("file", file);
  if (Object.keys(choices.columnOverrides).length > 0) {
    form.append("column_overrides", JSON.stringify(choices.columnOverrides));
  }
  if (choices.accountNameColumn) form.append("account_name_column", choices.accountNameColumn);
  if (choices.projectCode.trim()) form.append("project_code", choices.projectCode.trim());
  form.append("country_prefix", choices.countryPrefix);
  form.append("max_amount_threshold", String(choices.maxAmountThreshold));
  return form;
}

/** One or more Transaction Statements, plus the Process Maker file to reconcile against. */
export function statementForm(statements: File[], input: File | null, countryPrefix: string): FormData {
  const form = new FormData();
  for (const statement of statements) form.append("statement_files", statement);
  if (input) form.append("input_file", input);
  form.append("country_prefix", countryPrefix);
  return form;
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = response.statusText || `HTTP ${response.status}`;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const value = (body as { detail: unknown }).detail;
      detail = typeof value === "string" ? value : JSON.stringify(value);
    }
  } catch {
    // Not JSON; the status text will do.
  }
  return new ApiError(response.status, detail);
}

async function post(path: string, body: FormData | null, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(path, {
    method: "POST",
    headers: CLIENT_HEADER,
    body,
    signal,
  });
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function getSettings(signal?: AbortSignal): Promise<UiDefaults> {
  const response = await fetch("/settings", { signal });
  if (!response.ok) throw await errorFrom(response);
  return (await response.json()) as UiDefaults;
}

export async function previewUpload(form: FormData, signal?: AbortSignal): Promise<UploadCheck> {
  return (await (await post("/preview", form, signal)).json()) as UploadCheck;
}

export async function buildStatementReport(form: FormData, signal?: AbortSignal): Promise<StatementReport> {
  return (await (await post("/statement-report", form, signal)).json()) as StatementReport;
}

export function statementWorkbookPath(kind: StatementWorkbook): string {
  return `/statement-report/workbook?kind=${kind}`;
}

export async function shutDown(): Promise<void> {
  await post("/shutdown", null);
}

/** The download name the API chose, from its Content-Disposition header. */
export function filenameFrom(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return fallback;
    }
  }
  const plain = /filename="([^"]+)"/i.exec(disposition);
  return plain?.[1] ?? fallback;
}

/** POST a form, then hand the workbook that comes back to the browser to save. */
export async function downloadWorkbook(path: string, form: FormData, fallback: string): Promise<void> {
  const response = await post(path, form);
  const name = filenameFrom(response.headers.get("Content-Disposition"), fallback);
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
  } finally {
    // Give the browser a moment to start the save before the blob goes away.
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
}
