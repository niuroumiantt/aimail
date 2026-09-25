import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import App from "./App";

afterEach(() => window.history.pushState({}, "", "/"));

it("shell renders the product name", async () => {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "aimail" })).toBeInTheDocument();
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
