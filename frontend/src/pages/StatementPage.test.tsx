import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StatementPage, type StatementSettings } from "./StatementPage";
import type { StatementFileSummary, StatementReport, StatementTransaction } from "../api/client";
import { csvFile, json, mockApi, sentForm } from "../test/fixtures";

const SETTINGS: StatementSettings = { blocked: false, countryPrefix: "254" };

function txn(overrides: Partial<StatementTransaction> = {}): StatementTransaction {
  return {
    file_name: "statement.xlsx",
    row_number: 2,
    status: "Successful",
    is_successful: true,
    account_number: "254712345678",
    account_name: "TEST001",
    remark: "C#37154 13054AF RESP AIRTIME-KSH100 d05",
    remark_parts: ["37154", "13054AF", "100", "d05"],
    amount: 100,
    reference_id: "",
    date_raw: "2026-08-25 10:00",
    ...overrides,
  } as StatementTransaction;
}

function fileSummary(overrides: Partial<StatementFileSummary> = {}): StatementFileSummary {
  return {
    file_name: "statement.xlsx",
    total_rows: 1,
    successful_count: 1,
    unsuccessful_count: 0,
    counts_by_status: { Successful: 1 },
    total_disbursed: 100,
    footer_total: 100,
    footer_matches: true,
    success_rate: 1,
    unparsed_remarks: 0,
    unparsed_dates: 0,
    ...overrides,
  };
}

function makeReport(overrides: Partial<StatementReport> = {}): StatementReport {
  const paid = txn();
  const summary = fileSummary();
  return {
    file_summaries: [summary],
    combined: summary,
    transactions: [paid],
    unsuccessful_transactions: [],
    case_rollups: [
      {
        case_number: "37154",
        project_code: "13054AF",
        activity_code: "d05",
        remark_amount: 100,
        total_rows: 1,
        successful_count: 1,
        unsuccessful_count: 0,
        disbursed_total: 100,
        difference: 0,
      },
    ],
    warnings: [],
    errors: [],
    reconciliation: null,
    ...overrides,
  } as StatementReport;
}

function statementFile(name = "statement.xlsx"): File {
  return new File(["x"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

async function uploadStatements(...names: string[]) {
  const user = userEvent.setup();
  render(<StatementPage settings={SETTINGS} />);
  await user.upload(
    screen.getByLabelText(/Transaction Statement file/),
    (names.length ? names : ["statement.xlsx"]).map((name) => statementFile(name)),
  );
  return user;
}

describe("StatementPage", () => {
  it("asks for a statement first", () => {
    render(<StatementPage settings={SETTINGS} />);
    expect(screen.getByText(/Upload at least one Transaction Statement/)).toBeInTheDocument();
  });

  it("reports a fully paid statement and offers both downloads", async () => {
    const fetchMock = mockApi({ "/statement-report": () => json(makeReport()) });

    await uploadStatements();

    expect(await screen.findByText("Every payment in every statement went through.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Statement Report (Excel)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finance Reconciliation (Excel)" })).toBeInTheDocument();
    const form = sentForm(fetchMock, "/statement-report");
    expect(form.getAll("statement_files")).toHaveLength(1);
    expect(form.get("input_file")).toBeNull();
    expect(form.get("country_prefix")).toBe("254");
  });

  it.each([
    ["Statement Report (Excel)", "report", "C#37154 13054AF RESP AIRTIME-KSH100 d05_report.xlsx"],
    ["Finance Reconciliation (Excel)", "finance", "C#37154 13054AF RESP AIRTIME-KSH100 d05.xlsx"],
  ])("%s posts the same files and saves under the API's name", async (label, kind, name) => {
    const fetchMock = mockApi({
      "/statement-report": () => json(makeReport()),
      [`/statement-report/workbook?kind=${kind}`]: () =>
        new Response(new Blob(["xlsx"]), {
          headers: { "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(name)}` },
        }),
    });
    const createUrl = vi.fn(() => "blob:workbook");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }));
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });

    const user = await uploadStatements();
    await user.click(await screen.findByRole("button", { name: label }));

    await vi.waitFor(() => expect(saved).toEqual([name]));
    const form = sentForm(fetchMock, `/statement-report/workbook?kind=${kind}`);
    expect(form.getAll("statement_files")).toHaveLength(1);
    expect(form.get("country_prefix")).toBe("254");
  });

  it("puts failed payments first, open, with a blank amount for a reversal", async () => {
    const reversed = txn({ status: "Reversed", is_successful: false, amount: null, reference_id: "T-1", row_number: 3 });
    const summary = fileSummary({
      total_rows: 2,
      unsuccessful_count: 1,
      counts_by_status: { Successful: 1, Reversed: 1 },
      footer_total: null,
      footer_matches: null,
    });
    mockApi({
      "/statement-report": () =>
        json(makeReport({ combined: summary, file_summaries: [summary], transactions: [txn(), reversed], unsuccessful_transactions: [reversed] })),
    });

    await uploadStatements();

    expect(await screen.findByText(/payment\(s\) did NOT go through/)).toHaveTextContent("1");
    const panel = screen.getByText("Payments that did not go through (1)").closest("details") as HTMLElement;
    expect(panel).toHaveAttribute("open");
    const row = within(panel).getByRole("row", { name: /Reversed/ });
    expect(row).toHaveTextContent("T-1");
    expect(row).not.toHaveTextContent("null");
  });

  it("flags a case paid differently from its reference, outside the closed panel", async () => {
    mockApi({
      "/statement-report": () =>
        json(
          makeReport({
            case_rollups: [
              {
                case_number: "37154",
                project_code: "13054AF",
                activity_code: "d05",
                remark_amount: 29400,
                total_rows: 1,
                successful_count: 1,
                unsuccessful_count: 0,
                disbursed_total: 28000,
                difference: -1400,
              },
            ],
          }),
        ),
    });

    await uploadStatements();

    const warning = await screen.findByText(/the case reference says/);
    expect(warning).toHaveTextContent("KES 29,400");
    expect(warning).toHaveTextContent("KES 28,000");
    expect(warning).toHaveTextContent("-1,400");
    expect(warning.closest("details")).toBeNull();
  });

  it("shows a dash, not a figure, for a short reference with no amount", async () => {
    mockApi({
      "/statement-report": () =>
        json(
          makeReport({
            case_rollups: [
              { case_number: "38305", project_code: "", activity_code: "", remark_amount: null, total_rows: 1, successful_count: 1, unsuccessful_count: 0, disbursed_total: 100, difference: null },
            ],
          }),
        ),
    });

    await uploadStatements();

    const row = (await screen.findByRole("row", { name: /38305/, hidden: true })) as HTMLElement;
    expect(within(row).getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText(/the case reference says/)).toBeNull();
  });

  it("warns when OpenFloat's own total disagrees", async () => {
    const summary = fileSummary({ footer_total: 150, footer_matches: false });
    mockApi({ "/statement-report": () => json(makeReport({ combined: summary, file_summaries: [summary] })) });

    await uploadStatements();

    expect(await screen.findByText(/does not match the successful payments we counted/)).toBeInTheDocument();
  });

  it("lists files that could not be read and still reports the rest", async () => {
    mockApi({ "/statement-report": () => json(makeReport({ errors: ["corrupt.xlsx: not an Excel file"] })) });

    await uploadStatements("statement.xlsx", "corrupt.xlsx");

    expect(await screen.findByText(/corrupt.xlsx: not an Excel file/)).toBeInTheDocument();
    expect(screen.getByText("Every payment in every statement went through.")).toBeInTheDocument();
  });

  it("says so when nothing on the statement is a transaction", async () => {
    mockApi({ "/statement-report": () => json(makeReport({ transactions: [], unsuccessful_transactions: [] })) });

    await uploadStatements();

    expect(await screen.findByText(/No transactions were found/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Excel/ })).toBeNull();
  });

  it("reconciles against the Process Maker file", async () => {
    const entry = { phone: "254733345678", unique_id: "TEST006", input_amount: 100, input_row_numbers: [7], successful_count: 0, unsuccessful_count: 0, successful_total: 0, notes: [] };
    const fetchMock = mockApi({
      "/statement-report": (init) =>
        json(
          (init?.body as FormData).get("input_file")
            ? makeReport({
                reconciliation: {
                  input_rows: 2,
                  matched_paid: [],
                  matched_not_paid: [],
                  missing_from_statement: [entry],
                  statement_not_in_input: [],
                  duplicate_input_phones: [],
                  multiply_paid_phones: ["254752345678"],
                },
              })
            : makeReport(),
        ),
    });

    const user = await uploadStatements();
    await screen.findByText("Every payment in every statement went through.");
    await user.upload(screen.getByLabelText(/Process Maker export you prepared/), csvFile());

    expect(await screen.findByText("Compared with your Process Maker file")).toBeInTheDocument();
    expect(screen.getByText(/are not on any statement you uploaded/)).toHaveTextContent("1");
    expect(screen.getByText(/paid more than once: 254752345678/)).toBeInTheDocument();
    expect(screen.getByText(/plus the four reconciliation sheets/)).toBeInTheDocument();
    expect(sentForm(fetchMock, "/statement-report").get("input_file")).toBeInstanceOf(File);
  });

  it("blames the Process Maker file for a 400", async () => {
    mockApi({
      "/statement-report": (init) =>
        (init?.body as FormData).get("input_file")
          ? json({ detail: "Unsupported file type: .txt" }, 400)
          : json(makeReport()),
    });

    const user = await uploadStatements();
    await screen.findByText("Every payment in every statement went through.");
    await user.upload(screen.getByLabelText(/Process Maker export you prepared/), csvFile());

    expect(await screen.findByText(/We couldn't open your Process Maker file/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Remove/ }));
    expect(await screen.findByText("Every payment in every statement went through.")).toBeInTheDocument();
  });

  it("refuses an oversized statement without sending it", async () => {
    const fetchMock = mockApi({});
    const user = userEvent.setup();
    render(<StatementPage settings={SETTINGS} />);
    const big = statementFile("huge.xlsx");
    Object.defineProperty(big, "size", { value: 21 * 1024 * 1024 });

    await user.upload(screen.getByLabelText(/Transaction Statement file/), big);

    expect(screen.getByText(/'huge.xlsx' is larger than 20 MB/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
