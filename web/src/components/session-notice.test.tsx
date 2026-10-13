import { act, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { SESSION_EXPIRED_EVENT } from "@/lib/session-auth";
import { SessionNotice } from "./session-notice";

it("offers one explicit login action after expiry and does not navigate automatically", () => {
  const original = window.location.href;
  render(<SessionNotice />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  act(() => { window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)); window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)); });
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  const link = screen.getByRole("link", { name: "重新登录" });
  expect(link).toHaveAttribute("href", `/oauth2/start?rd=${encodeURIComponent(original)}`);
  expect(window.location.href).toBe(original);
});
