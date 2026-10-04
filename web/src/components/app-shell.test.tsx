import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

vi.mock("./account-menu", () => ({ AccountMenu: () => null }));
beforeEach(() => localStorage.clear());
const props = { sidebar: <nav>Folders</nav>, list: <div>Messages</div>, detail: <div>Reading</div>, showDetail: true, readerKey: "sales:1" };

it("resizes by keyboard, clamps, persists and resets without changing the reader", () => {
  const view = render(<AppShell {...props} />);
  const handle = screen.getByRole("separator", { name: "调整邮件列表宽度" });
  fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(handle).toHaveAttribute("aria-valuenow", "364");
  expect(JSON.parse(localStorage.getItem("aimail-inbox-layout")!).width).toBe(364);
  for (let i = 0; i < 30; i++) fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(handle).toHaveAttribute("aria-valuenow", "600");
  view.unmount();
  render(<AppShell {...props} />);
  expect(screen.getByRole("separator", { name: "调整邮件列表宽度" })).toHaveAttribute("aria-valuenow", "600");
  fireEvent.doubleClick(screen.getByRole("separator", { name: "调整邮件列表宽度" }));
  expect(screen.getByRole("separator", { name: "调整邮件列表宽度" })).toHaveAttribute("aria-valuenow", "352");
  expect(screen.getByText("Reading")).toBeInTheDocument();
});

it("auto hides when reading, can always reopen, and reopens when leaving the reader", () => {
  const view = render(<AppShell {...props} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "阅读时隐藏" }));
  expect(screen.getByRole("region", { name: "列表" })).toHaveClass("mail-list-collapsed");
  fireEvent.click(screen.getByRole("button", { name: "展开邮件列表" }));
  expect(screen.getByRole("region", { name: "列表" })).not.toHaveClass("mail-list-collapsed");
  view.rerender(<AppShell {...props} readerKey="sales:2" />);
  expect(screen.getByRole("button", { name: "展开邮件列表" })).toBeInTheDocument();
  view.rerender(<AppShell {...props} readerKey="larry:" showDetail={false} />);
  expect(screen.getByRole("region", { name: "列表" })).not.toHaveClass("mail-list-collapsed");
  expect(JSON.parse(localStorage.getItem("aimail-inbox-layout")!).autoHide).toBe(true);
  view.unmount();
  render(<AppShell {...props} />);
  expect(screen.getByRole("button", { name: "展开邮件列表" })).toBeInTheDocument();
});

it("supports manual collapse and survives malformed stored settings", () => {
  localStorage.setItem("aimail-inbox-layout", "broken JSON");
  render(<AppShell {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "收起邮件列表" }));
  expect(screen.getByRole("region", { name: "列表" })).toHaveClass("mail-list-collapsed");
  fireEvent.click(screen.getByRole("button", { name: "展开邮件列表" }));
  expect(screen.getByRole("region", { name: "列表" })).not.toHaveClass("mail-list-collapsed");
});

it("keeps navigation reachable on a narrow screen and persists desktop navigation width", () => {
  const width = window.innerWidth;
  Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
  const view = render(<AppShell {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "展开主导航" }));
  expect(view.container.querySelector(".mail-navigation")).toHaveAttribute("data-overlay", "true");
  fireEvent.click(screen.getByRole("button", { name: "隐藏左侧导航" }));
  expect(view.container.querySelector(".mail-navigation")).toHaveAttribute("data-overlay", "false");
  Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  fireEvent(window, new Event("resize"));
  fireEvent.keyDown(screen.getByRole("separator", { name: "调整左侧导航宽度" }), { key: "ArrowRight" });
  expect(JSON.parse(localStorage.getItem("aimail-navigation-layout")!).width).toBe(228);
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
});
