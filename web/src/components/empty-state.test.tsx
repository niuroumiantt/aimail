import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EmptyState } from "./empty-state";

it("empty state renders its action", () => {
  render(<EmptyState title="空" subtitle="没有" action={<button>看全部</button>} />);
  expect(screen.getByRole("heading", { name: "空" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "看全部" })).toBeInTheDocument();
});
