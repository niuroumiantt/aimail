import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import App from "./App";

afterEach(() => window.history.pushState({}, "", "/"));

it("shell offers the shared product link back to the inbox", async () => {
  render(<App />);
  expect(await screen.findByRole("link", { name: "Aimail 首页" })).toHaveAttribute("href", "/");
});

it("thread page shows the messages from the detail which the list does not carry", async () => {
  window.history.pushState({}, "", "/t/t-aurora");
  render(<App />);
  expect(await screen.findByText(/We are expanding our Helsinki data center/)).toBeInTheDocument();
  expect(await screen.findByText("第一次来信")).toBeInTheDocument();
});

it("opens AI reading as a hidden right panel from the production inbox", async () => {
  window.history.pushState({}, "", "/t/t-aurora");
  render(<App />);
  const trigger = await screen.findByRole("button", { name: "AI 阅读" });
  expect(screen.queryByRole("complementary", { name: "AI 阅读" })).not.toBeInTheDocument();
  fireEvent.click(trigger);
  expect(await screen.findByRole("complementary", { name: "AI 阅读" })).toBeInTheDocument();
  expect(screen.getByText("AI 接口尚未配置")).toBeInTheDocument();
});

it("opens and closes the same reply composer from the command bar", async () => {
  localStorage.clear();
  window.history.pushState({}, "", "/t/t-aurora");
  render(<App />);
  await screen.findByText(/We are expanding our Helsinki data center/);
  const reply = screen.getByRole("button", { name: "回复" });
  expect(reply).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(reply);
  expect(reply).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("textbox", { name: "正文" })).toBeInTheDocument();
  fireEvent.click(reply);
  expect(screen.queryByRole("textbox", { name: "正文" })).not.toBeInTheDocument();
  expect(screen.getByText(/We are expanding our Helsinki data center/)).toBeInTheDocument();
});

it("focuses the global search with slash but leaves editable input alone", async () => {
  window.history.pushState({}, "", "/");
  render(<App />);
  await screen.findByText("Mikko Laine");
  const search = screen.getByRole("searchbox");
  fireEvent.keyDown(document.body, { key: "/" });
  expect(search).toHaveFocus();
  fireEvent.change(search, { target: { value: "Helsinki" } });
  expect(screen.getByRole("link", { name: /RFQ – 48/ })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /DDR5 RDIMM/ })).not.toBeInTheDocument();
  const key = new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true });
  search.dispatchEvent(key);
  expect(key.defaultPrevented).toBe(false);
});
