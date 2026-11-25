import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TransformPage, type TransformSettings } from "./TransformPage";
import { csvFile, json, makeCheck, mockApi, sentForm } from "../test/fixtures";

const SETTINGS: TransformSettings = {
  blocked: false,
  countryPrefix: "254",
  maxAmountThreshold: 10000,
  defaultAccountNameColumn: null,
  defaultProjectCode: null,
};

async function upload(settings: TransformSettings = SETTINGS) {
  const user = userEvent.setup();
  render(<TransformPage settings={settings} />);
  await user.upload(screen.getByLabelText(/Process Maker airtime export/), csvFile());
  return user;
}

describe("TransformPage", () => {
  it("asks for a file first", () => {
    render(<TransformPage settings={SETTINGS} />);
    expect(screen.getByText(/Upload a file to get started/)).toBeInTheDocument();
  });

  it("walks a clean file through to the download", async () => {
    const fetchMock = mockApi({ "/preview": () => json(makeCheck()) });

    await upload();

    expect(await screen.findByRole("button", { name: "Download 2 rows for OpenFloat" })).toBeInTheDocument();
    expect(screen.getByText("Every row in this file can be uploaded.")).toBeInTheDocument();
    expect(screen.getByText(/Account Name will use/)).toHaveTextContent("e.g. TEST001, TEST002");
    // A recognised file needs no interaction, so the mapping stays closed.
    expect(screen.getByText("Column mapping").closest("details")).not.toHaveAttribute("open");
    expect(sentForm(fetchMock, "/preview").get("country_prefix")).toBe("254");
  });

  it("opens the mapping when a field is missing, and re-checks after a pick", async () => {
    const missing = makeCheck(
      {
        columns: ["unique_id", "airtime_phone", "network", "Payout"],
        mapping: { airtime_phone: "airtime_phone", network: "network" },
        missing_fields: ["amount"],
      },
      { output_row_count: 0, report: { total_rows: 2, valid_rows: 0, errors: [], warnings: [] } },
    );
    const fetchMock = mockApi({
      "/preview": (init) =>
        json((init?.body as FormData).get("column_overrides") ? makeCheck() : missing),
    });

    const user = await upload();

    expect(await screen.findByText(/No column chosen for/)).toHaveTextContent("Amount");
    expect(screen.getByText(/Column mapping \(1 not found\)/).closest("details")).toHaveAttribute("open");
    expect(screen.getByText(/There is nothing to download/)).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Amount" }), "Payout");

    expect(await screen.findByRole("button", { name: "Download 2 rows for OpenFloat" })).toBeInTheDocument();
    expect(sentForm(fetchMock, "/preview").get("column_overrides")).toBe('{"amount":"Payout"}');
  });

  it("lists rows that will be left out and warns beside the download", async () => {
    const issue = { row_number: 3, severity: "error" as const, field: "airtime_phone", message: "Row 3: Phone number must be 9 digits" };
    mockApi({
      "/preview": () =>
        json(makeCheck({}, { report: { total_rows: 2, valid_rows: 1, errors: [issue], warnings: [] }, output_row_count: 1 })),
    });

    await upload();

    const panel = (await screen.findByText("Rows that will be left out (1)")).closest("details");
    expect(panel).not.toBeNull();
    const row = within(panel as HTMLElement).getByRole("row", { name: /Phone number must be 9 digits/ });
    expect(row).toHaveTextContent("Phone number");
    expect(row).not.toHaveTextContent("Row 3:");
    expect(screen.getByText(/missing 1 row\(s\)/)).toBeInTheDocument();
  });

  it("explains a file it can't open, with the technical detail tucked away", async () => {
    mockApi({ "/preview": () => json({ detail: "Unsupported file type: .txt" }, 400) });

    await upload();

    expect(await screen.findByText(/We couldn't open this file/)).toBeInTheDocument();
    expect(screen.getByText(/Technical details/).closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/Unsupported file type: \.txt/)).toBeInTheDocument();
  });

  it("refuses an oversized file without sending it", async () => {
    const fetchMock = mockApi({});
    const user = userEvent.setup();
    render(<TransformPage settings={SETTINGS} />);
    const big = csvFile("huge.csv");
    Object.defineProperty(big, "size", { value: 21 * 1024 * 1024 });

    await user.upload(screen.getByLabelText(/Process Maker airtime export/), big);

    expect(await screen.findByText(/larger than 20 MB/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the project code box for short case references and sends what is typed", async () => {
    const fetchMock = mockApi({
      "/preview": () => json(makeCheck({ short_form_rows: 2, remark_preview: "C#38305" })),
    });

    const user = await upload();

    expect(await screen.findByText(/2 row\(s\) carry a short case reference/)).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /Project code/ }), "22505AA");

    await waitFor(() => expect(sentForm(fetchMock, "/preview").get("project_code")).toBe("22505AA"));
  });

  it("starts the identifier and project code from .env", async () => {
    const fetchMock = mockApi({ "/preview": () => json(makeCheck()) });

    await upload({ ...SETTINGS, defaultAccountNameColumn: "Staff ID", defaultProjectCode: "22505AA" });

    await screen.findByRole("button", { name: /Download/ });
    const form = sentForm(fetchMock, "/preview");
    expect(form.get("account_name_column")).toBe("Staff ID");
    expect(form.get("project_code")).toBe("22505AA");
  });

  it("does nothing while a sidebar setting is invalid", () => {
    render(<TransformPage settings={{ ...SETTINGS, blocked: true }} />);
    expect(screen.getByText(/Fix the setting under/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Process Maker airtime export/)).toBeNull();
  });
});
