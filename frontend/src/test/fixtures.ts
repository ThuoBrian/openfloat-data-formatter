/** Synthetic API responses. No real data, ever. */
import { vi } from "vitest";

import type { UiDefaults, UploadCheck, UploadPreview } from "../api/client";

export const DEFAULTS: UiDefaults = {
  default_country_prefix: "254",
  max_amount_threshold: 10000,
  project_code: null,
  account_name_column: null,
  version: "0.1.0",
};

export function makeCheck(preview: Partial<UploadPreview> = {}, check: Partial<UploadCheck> = {}): UploadCheck {
  return {
    preview: {
      columns: ["unique_id", "airtime_phone", "network", "amount"],
      row_count: 2,
      detected: { airtime_phone: "airtime_phone", network: "network", amount: "amount" },
      mapping: { airtime_phone: "airtime_phone", network: "network", amount: "amount" },
      missing_fields: [],
      mapping_warnings: [],
      identifier_column: "unique_id",
      identifier_filled: 2,
      identifier_samples: ["TEST001", "TEST002"],
      preview_columns: ["unique_id", "airtime_phone", "network", "amount"],
      preview_rows: [
        ["TEST001", "712345678", "Safaricom", "150"],
        ["TEST002", "798765432", "Airtel", "200"],
      ],
      short_form_rows: 0,
      project_code_column: null,
      remark_preview: null,
      remark_readable: false,
      ...preview,
    },
    report: { total_rows: 2, valid_rows: 2, errors: [], warnings: [] },
    output_row_count: 2,
    ...check,
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>;

/** Replace fetch with a router keyed by path; records every call. */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const handler = routes[path];
    if (!handler) throw new Error(`Unexpected request to ${path}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The FormData sent in the nth call to `path`. */
export function sentForm(fetchMock: ReturnType<typeof mockApi>, path: string, nth = -1): FormData {
  const calls = fetchMock.mock.calls.filter(([input]) => String(input) === path);
  const call = calls.at(nth);
  if (!call) throw new Error(`No request to ${path}`);
  return call[1]?.body as FormData;
}

export function csvFile(name = "export.csv"): File {
  return new File(["unique_id,airtime_phone\nTEST001,712345678\n"], name, { type: "text/csv" });
}
