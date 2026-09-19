import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { ThemeToggle } from "./theme-toggle";
import { TipProvider } from "./tip";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

it("theme toggle stamps data-theme on the root and clears it for system", () => {
  render(
    <TipProvider>
      <ThemeToggle />
    </TipProvider>,
  );
  const button = screen.getByRole("button");
  expect(document.documentElement.dataset.theme).toBeUndefined();
  fireEvent.click(button); // system → light
  expect(document.documentElement.dataset.theme).toBe("light");
  fireEvent.click(button); // light → dark
  expect(document.documentElement.dataset.theme).toBe("dark");
  fireEvent.click(button); // dark → system
  expect(document.documentElement.dataset.theme).toBeUndefined();
});
