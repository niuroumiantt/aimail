import { useEffect } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

vi.mock("./account-menu", () => ({ AccountMenu: () => null }));
const originalWidth = window.innerWidth;
beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "innerWidth", { value: 1600, configurable: true });
});
afterEach(() => Object.defineProperty(window, "innerWidth", { value: originalWidth, configurable: true }));
const props = { sidebar: <nav>Folders</nav>, list: <div>Messages</div>, detail: <div>Reading</div>, showDetail: true, readerKey: "sales:1" };

it("resizes by keyboard, clamps, persists and resets without changing the reader", () => {
  const view = render(<AppShell {...props} />);
  const handle = screen.getByRole("separator", { name: "调整邮件列表宽度" });
  fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(handle).toHaveAttribute("aria-valuenow", "372");
  expect(JSON.parse(localStorage.getItem("aimail-inbox-layout")!).width).toBe(372);
  for (let i = 0; i < 30; i++) fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(handle).toHaveAttribute("aria-valuenow", "600");
  view.unmount();
  render(<AppShell {...props} />);
  expect(screen.getByRole("separator", { name: "调整邮件列表宽度" })).toHaveAttribute("aria-valuenow", "600");
  fireEvent.doubleClick(screen.getByRole("separator", { name: "调整邮件列表宽度" }));
  expect(screen.getByRole("separator", { name: "调整邮件列表宽度" })).toHaveAttribute("aria-valuenow", "360");
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
  expect(JSON.parse(localStorage.getItem("aimail-navigation-layout")!).width).toBe(232);
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
});


it("resizes and remembers the customer pane, then restores it after hiding", () => {
  const view = render(<AppShell {...props} customer={<div>Latest business overview</div>} />);
  const handle = screen.getByRole("separator", { name: "调整正文与客户工作区宽度" });
  fireEvent.keyDown(handle, { key: "ArrowLeft" });
  expect(handle).toHaveAttribute("aria-valuenow", "332");
  expect(JSON.parse(localStorage.getItem("aimail-customer-layout")!).width).toBe(332);
  fireEvent.click(screen.getByRole("button", { name: "收起客户工作区" }));
  expect(screen.queryByRole("complementary", { name: "客户需求栏" })).not.toBeInTheDocument();
  expect(screen.getByText("Reading")).toBeInTheDocument();
  view.unmount();
  render(<AppShell {...props} customer={<div>Latest business overview</div>} />);
  expect(screen.queryByRole("complementary", { name: "客户需求栏" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "展开客户工作区" }));
  expect(screen.getByRole("separator", { name: "调整正文与客户工作区宽度" })).toHaveAttribute("aria-valuenow", "332");
  fireEvent.keyDown(screen.getByRole("separator", { name: "调整正文与客户工作区宽度" }), { key: "Home" });
  expect(JSON.parse(localStorage.getItem("aimail-customer-layout")!).width).toBe(320);
});

it("temporarily devotes the workspace to the reader and restores each pane without changing saved preferences", () => {
  localStorage.setItem("aimail-inbox-layout", JSON.stringify({ width: 420, autoHide: true }));
  const view = render(<AppShell {...props} customer={<div>Business</div>} />);
  fireEvent.click(screen.getByRole("button", { name: "展开邮件列表" }));
  fireEvent.click(screen.getByRole("button", { name: "邮件全屏" }));
  expect(view.container.querySelector(".mail-app-shell")).toHaveClass("mail-reader-focused");
  expect(screen.queryByRole("region", { name: "列表" })).not.toBeInTheDocument();
  expect(screen.queryByRole("complementary", { name: "客户需求栏" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "展开邮件列表" })).not.toBeInTheDocument();
  expect(screen.getByText("Reading")).toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("aimail-inbox-layout")!)).toEqual({ width: 420, autoHide: true });
  fireEvent.click(screen.getByRole("button", { name: "退出邮件全屏" }));
  expect(screen.getByRole("region", { name: "列表" })).not.toHaveClass("mail-list-collapsed");
  expect(screen.getByRole("complementary", { name: "客户需求栏" })).toBeInTheDocument();
  expect(screen.getByRole("separator", { name: "调整邮件列表宽度" })).toHaveAttribute("aria-valuenow", "420");
});

it("retains usable reader space with large stored pane widths on a smaller desktop", () => {
  Object.defineProperty(window, "innerWidth", { value: 1100, configurable: true });
  localStorage.setItem("aimail-inbox-layout", JSON.stringify({ width: 600 }));
  localStorage.setItem("aimail-customer-layout", JSON.stringify({ width: 520 }));
  const view = render(<AppShell {...props} customer={<div>Business</div>} />);
  const listWidth = Number(screen.getByRole("separator", { name: "调整邮件列表宽度" }).getAttribute("aria-valuenow"));
  const customerWidth = Number(screen.getByRole("separator", { name: "调整正文与客户工作区宽度" }).getAttribute("aria-valuenow"));
  expect(1100 - 26 - 44 - listWidth - customerWidth).toBeGreaterThanOrEqual(360);
  expect(view.container.querySelector(".mail-navigation")).toHaveAttribute("data-compact", "true");
  expect(JSON.parse(localStorage.getItem("aimail-customer-layout")!).width).toBe(520);
  fireEvent.click(screen.getByRole("button", { name: "隐藏客户工作区" }));
  expect(Number(screen.getByRole("separator", { name: "调整邮件列表宽度" }).getAttribute("aria-valuenow"))).toBeGreaterThan(listWidth);
});

it("opens the customer overlay on mobile without replacing the saved desktop layout", () => {
  Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
  localStorage.setItem("aimail-customer-layout", JSON.stringify({ width: 400, collapsed: true }));
  const view = render(<AppShell {...props} customer={<div>Business</div>} />);
  fireEvent.click(screen.getByRole("button", { name: "展开客户工作区" }));
  expect(view.container.querySelector(".mail-customer-pane")).toHaveAttribute("data-open", "true");
  expect(screen.getByRole("complementary", { name: "客户需求栏" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "收起客户工作区" }));
  expect(screen.queryByRole("complementary", { name: "客户需求栏" })).not.toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("aimail-customer-layout")!)).toEqual({ width: 400, collapsed: true });
});

it("budgets the application rail and card gutters when the customer pane is open", () => {
  Object.defineProperty(window, "innerWidth", { value: 1100, configurable: true });
  localStorage.setItem("aimail-inbox-layout", JSON.stringify({ width: 600 }));
  localStorage.setItem("aimail-customer-layout", JSON.stringify({ width: 520, collapsed: false }));
  render(<AppShell {...props} toolbar={<div>Commands</div>} rail={<nav>Apps</nav>} customer={<div>Business</div>} />);
  const listWidth = Number(screen.getByRole("separator", { name: "调整邮件列表宽度" }).getAttribute("aria-valuenow"));
  const customerWidth = Number(screen.getByRole("separator", { name: "调整正文与客户工作区宽度" }).getAttribute("aria-valuenow"));
  expect(1100 - 72 - 52 - 44 - listWidth - customerWidth).toBeGreaterThanOrEqual(360);
});


it("does not mount customer analysis while the customer workspace is hidden", () => {
  const load = vi.fn();
  function CustomerAnalysis() {
    useEffect(() => { load(); }, []);
    return <div>Customer overview</div>;
  }
  localStorage.setItem("aimail-customer-layout", JSON.stringify({ width: 320, collapsed: true }));
  render(<AppShell {...props} customer={<CustomerAnalysis />} />);
  expect(load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "邮件全屏" }));
  expect(load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "退出邮件全屏" }));
  expect(load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "展开客户工作区" }));
  expect(load).toHaveBeenCalledOnce();
});

it("keeps message actions inside the reader and model settings in the application header", () => {
  const view = render(<AppShell {...props} toolbar={<button>Reply to selected mail</button>} rail={<nav>Apps</nav>} modelControl={<button>Model settings</button>} customer={<div>Business</div>} customerInitiallyCollapsed />);
  const reader = view.container.querySelector('.mail-reader-pane')!;
  expect(reader).toContainElement(screen.getByRole('button', { name: 'Reply to selected mail' }));
  expect(reader).toContainElement(screen.getByRole('button', { name: '邮件全屏' }));
  expect(reader).not.toContainElement(screen.getByRole('button', { name: 'Model settings' }));
  expect(screen.getByRole('button', { name: '展开客户工作区' })).toHaveTextContent('已收起');
  fireEvent.click(screen.getByRole('button', { name: '邮件全屏' }));
  fireEvent.click(screen.getByRole('button', { name: '展开客户工作区' }));
  expect(view.container.querySelector('.mail-app-shell')).not.toHaveClass('mail-reader-focused');
  expect(screen.getByRole('button', { name: '隐藏客户工作区' })).toHaveTextContent('已展开');
  expect(screen.getByRole('complementary', { name: '客户需求栏' })).toBeInTheDocument();
});


it("keeps AI reading reachable after entering mail fullscreen", () => {
  const view = render(<AppShell {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "邮件全屏" }));
  expect(view.container.querySelector(".mail-app-shell")).toHaveClass("mail-reader-focused");
  view.rerender(<AppShell {...props} assistantOpen />);
  expect(view.container.querySelector(".mail-app-shell")).not.toHaveClass("mail-reader-focused");
});
