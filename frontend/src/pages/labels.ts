/** Words for our field names, as the staff using the app would say them. */
import type { ValidationIssue } from "../api/client";

/** The fields a user can map by hand. Mirrors upload_preview.MAPPABLE_FIELDS. */
export const MAPPABLE_FIELDS: ReadonlyArray<readonly [field: string, label: string]> = [
  ["airtime_phone", "Phone number"],
  ["network", "Network / provider"],
  ["amount", "Amount"],
];

const FIELD_LABELS: Record<string, string> = {
  ...Object.fromEntries(MAPPABLE_FIELDS),
  account_name: "ID (Account Name)",
  case_remark: "Case reference",
  project_code: "Project code",
};

/** Validation issues name the canonical field; anything unlisted shows as-is. */
export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

/** Validator messages lead with "Row 5: …", which the Row column already says. */
export function issueRows(issues: ValidationIssue[]): string[][] {
  return issues.map((issue) => [
    String(issue.row_number),
    fieldLabel(issue.field),
    issue.message.replace(/^Row \d+:\s*/, ""),
  ]);
}

export const ISSUE_COLUMNS = ["Row", "Column", "Problem"];
