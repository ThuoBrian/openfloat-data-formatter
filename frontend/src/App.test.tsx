import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { CLIENT_HEADER } from "./api/client";
import { DEFAULTS, json, mockApi } from "./test/fixtures";

describe("App", () => {
  it("starts its settings from GET /settings", async () => {
    mockApi({ "/settings": () => json({ ...DEFAULTS, default_country_prefix: "255", max_amount_threshold: 5000 }) });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByText("Advanced settings"));

    expect(screen.getByRole("textbox", { name: "Country prefix" })).toHaveValue("255");
    expect(screen.getByRole("spinbutton", { name: /threshold/ })).toHaveValue(5000);
    expect(screen.getByText(/Version 0.1.0/)).toBeInTheDocument();
  });

  it("stops the page on a bad country prefix", async () => {
    mockApi({ "/settings": () => json(DEFAULTS) });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByText("Advanced settings"));
    const prefix = screen.getByRole("textbox", { name: "Country prefix" });
    await user.clear(prefix);
    await user.type(prefix, "+254");

    expect(screen.getByText(/must be 1 to 3 digits/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Process Maker airtime export/)).toBeNull();
  });

  it("closes the app only after confirming", async () => {
    const fetchMock = mockApi({
      "/settings": () => json(DEFAULTS),
      "/shutdown": () => json({ status: "stopping" }),
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Close the app" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/shutdown", expect.anything());

    const dialog = screen.getByRole("dialog", { name: "Close the app?" });
    await user.click(dialog.querySelector(".button-primary") as HTMLElement);

    expect(await screen.findByText("The app has closed.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/shutdown", expect.objectContaining({ headers: CLIENT_HEADER }));
  });

  it("says so when the API isn't there", async () => {
    mockApi({ "/settings": () => json({ detail: "down" }, 500) });

    render(<App />);

    expect(await screen.findByText(/The app isn't responding/)).toBeInTheDocument();
  });
});
