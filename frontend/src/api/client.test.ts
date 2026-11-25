import { describe, expect, it } from "vitest";

import { ApiError, CLIENT_HEADER, filenameFrom, previewUpload, uploadForm } from "./client";
import { json, makeCheck, mockApi } from "../test/fixtures";

const CHOICES = {
  columnOverrides: {},
  accountNameColumn: null,
  projectCode: "",
  countryPrefix: "254",
  maxAmountThreshold: 10000,
};

describe("uploadForm", () => {
  it("sends only the choices that were made", () => {
    const form = uploadForm(new File(["x"], "a.csv"), CHOICES);

    expect(form.get("file")).toBeInstanceOf(File);
    expect(form.get("column_overrides")).toBeNull();
    expect(form.get("account_name_column")).toBeNull();
    expect(form.get("project_code")).toBeNull();
    expect(form.get("country_prefix")).toBe("254");
    expect(form.get("max_amount_threshold")).toBe("10000");
  });

  it("encodes column picks as JSON and trims the project code", () => {
    const form = uploadForm(new File(["x"], "a.csv"), {
      ...CHOICES,
      columnOverrides: { amount: "Payout" },
      accountNameColumn: "Staff ID",
      projectCode: " 22505AA ",
    });

    expect(form.get("column_overrides")).toBe('{"amount":"Payout"}');
    expect(form.get("account_name_column")).toBe("Staff ID");
    expect(form.get("project_code")).toBe("22505AA");
  });
});

describe("requests", () => {
  it("carry the client header the API requires", async () => {
    const fetchMock = mockApi({ "/preview": () => json(makeCheck()) });

    await previewUpload(new FormData());

    expect(fetchMock.mock.calls[0]?.[1]?.headers).toEqual(CLIENT_HEADER);
  });

  it("turn an error status into an ApiError carrying the API's detail", async () => {
    mockApi({ "/preview": () => json({ detail: "Unsupported file type" }, 400) });

    const failure = previewUpload(new FormData());

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 400, message: "Unsupported file type" });
  });
});

describe("filenameFrom", () => {
  it("reads a plain name", () => {
    expect(filenameFrom('attachment; filename="input_openfloat.xlsx"', "x")).toBe("input_openfloat.xlsx");
  });

  it("decodes an RFC 5987 name", () => {
    expect(filenameFrom("attachment; filename*=UTF-8''Malipo%20%C3%A9.xlsx", "x")).toBe("Malipo é.xlsx");
  });

  it("falls back when there is no usable name", () => {
    expect(filenameFrom(null, "fallback.xlsx")).toBe("fallback.xlsx");
    expect(filenameFrom("attachment; filename*=UTF-8''%E0%A4", "fallback.xlsx")).toBe("fallback.xlsx");
  });
});
