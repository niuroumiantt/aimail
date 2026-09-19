import { render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import App from "./App";

afterEach(() => window.history.pushState({}, "", "/"));

it("shell renders the product name", async () => {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "mail2leads" })).toBeInTheDocument();
});

it("thread page shows the messages from the detail which the list does not carry", async () => {
  window.history.pushState({}, "", "/t/t-aurora");
  render(<App />);
  expect(await screen.findByText(/We are expanding our Helsinki data center/)).toBeInTheDocument();
  expect(await screen.findByText("第一次来信")).toBeInTheDocument();
});
