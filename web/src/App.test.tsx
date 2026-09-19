import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import App from "./App";

it("shell renders the product name", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "mail2leads" })).toBeInTheDocument();
});
