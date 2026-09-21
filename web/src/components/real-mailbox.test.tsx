import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { RealMailbox } from "./real-mailbox";

const thread = (id: number, contact: string, reading = null) => ({ id, subject: `RFQ ${id}`, contact, email: `${id}@example.test`, date: `2026-09-${id === 1 ? "19" : "18"}T08:00:00Z`, count: 1, preview: "Original preview", reading });
const original = (id: number, status?: string) => ({ id, subject: `RFQ ${id}`, from_name: `Customer ${id}`, from_email: `${id}@example.test`, to_emails: "sales@example.test", sent_at: "2026-09-19T08:00:00Z", body_new: `Actual original ${id}`, body_quoted: "Earlier original", attachments: [], reading: status ? { status, model: "test-model", task_version: "read@1", produced_at: "2026-09-19T09:00:00Z", payload: {} } : null });
const response = (data: unknown) => Promise.resolve(new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } }));
const mount = () => render(<MemoryRouter><RealMailbox /></MemoryRouter>);
afterEach(() => vi.unstubAllGlobals());

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "matchMedia", { writable: true, value: vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() })) });
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/threads") ? response({ address: "sales@example.test", messages: 2, threads: [thread(1, "Alpha"), thread(2, "Beta")], coverage: "INBOX · 最近30天", job: { status: "idle", kind: "" } }) : response({ messages: [original(url.endsWith("/2") ? 2 : 1)] })));
});

test("shows actual originals and never starts sync or inference on mount", async () => {
  mount();
  expect(await screen.findByText("Actual original 1")).toBeInTheDocument();
  expect(screen.getByText("原文已就绪，尚未分析")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === "GET")).toBe(true);
  expect(screen.queryByText("Aurora Compute")).not.toBeInTheDocument();
});

test("search and list hide/restore preserve real selection", async () => {
  mount(); await screen.findByText("Actual original 1");
  fireEvent.change(screen.getByLabelText("搜索已收取邮件"), { target: { value: "Beta" } });
  expect(document.querySelectorAll(".mw-mail-row")).toHaveLength(1);
  fireEvent.click(document.querySelector(".mw-mail-row")!);
  await screen.findByText("Actual original 2");
  fireEvent.click(screen.getByLabelText("隐藏邮件列表"));
  expect(document.querySelector(".mw-shell")).toHaveClass("mw-list-hidden");
  fireEvent.click(screen.getByLabelText("显示邮件列表"));
  expect(document.querySelector(".mw-shell")).not.toHaveClass("mw-list-hidden");
  expect(screen.getByText("Actual original 2")).toBeInTheDocument();
});

test("failed analysis is visible and retry is explicitly user initiated", async () => {
  const mock = vi.mocked(fetch), normal = mock.getMockImplementation()!;
  mock.mockImplementation((url, options) => String(url).endsWith("/analyze") ? response({ accepted: true }) : String(url).endsWith("/threads/1") ? response({ messages: [original(1, "failed")] }) : normal(url, options));
  mount(); await screen.findByText("本封分析失败，没有可用读数");
  const retry = screen.getByRole("button", { name: "重新分析" });
  fireEvent.click(retry);
  await waitFor(() => expect(mock.mock.calls.filter(([u]) => String(u).endsWith("/analyze"))).toHaveLength(1));
  expect(retry).toBeDisabled();
});

test("collapses overview without hiding the original", async () => {
  mount(); await screen.findByText("Actual original 1");
  fireEvent.click(screen.getByRole("button", { name: /专题总览.*收起/ }));
  expect(screen.queryByText("原文已就绪，尚未分析")).not.toBeInTheDocument();
  expect(screen.getByText("Actual original 1")).toBeInTheDocument();
});

test("service errors are explicit, not replaced by demo messages", async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Service unavailable" }), { status: 503 }));
  mount(); await screen.findByText("Service unavailable");
  expect(document.querySelectorAll(".mw-mail-row")).toHaveLength(0);
});
