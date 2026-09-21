import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MailFacts, type MailExtraction } from "./mail-facts";

afterEach(() => vi.unstubAllGlobals());
test("fixed two rows show grounded fields, missing values and clickable evidence", async () => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  const extraction: MailExtraction = { status: "ok", facts: [{ key: "company", value: "Acme", quote: "Acme needs 500 pcs" }, { key: "quantity", value: "500 pcs", quote: "Acme needs 500 pcs" }], model: "test", task_version: "extract_mail_facts@1", produced_at: "2026-09-20", source_id: 1, reason: "", coverage: "新增正文" };
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith("extraction") ? { enabled: true, counts: { ok: 1 } } : { messages: [{ id: 1, extraction }] })))));
  render(<MailFacts messageId={1} threadId={1} initial={extraction} />);
  expect(document.querySelectorAll(".mw-fact-row")).toHaveLength(2);
  expect(await screen.findByText("500 pcs")).toBeInTheDocument();
  expect(screen.getAllByText("未提供").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: /数量\s*500 pcs/ }));
  expect(await screen.findByText("Acme needs 500 pcs")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === "GET")).toBe(true);
});
