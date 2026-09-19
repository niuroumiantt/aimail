import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import App from "./App";

it("shell renders the product name", async () => {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "mail2leads" })).toBeInTheDocument();
});
