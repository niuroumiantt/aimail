import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RealMailboxAsk } from "./real-mailbox-ask";

const turn = { id: "one", question: "查找需求", status: "done", model: "local", task_version: "ask@1", scope: { total: 29, included: 29, truncated: 2 }, findings: [{ text: "客户需要服务器", quote: "Please quote servers", subject: "RFQ", source_id: 8, thread_id: 3, unverified: [] }] };
const response = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status }));
beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => vi.unstubAllGlobals());

test("restores actual answers and citation opens exact original", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response({ turns: [turn], job: { status: "done" } })));
  const citation = vi.fn();
  render(<RealMailboxAsk open onClose={() => {}} onBusy={() => {}} onCitation={citation} />);
  await screen.findByText("客户需要服务器");
  fireEvent.click(screen.getByRole("button", { name: /RFQ/ }));
  expect(citation).toHaveBeenCalledWith(3, 8);
  expect(screen.getByText(/本次提供 29 \/ 29/)).toBeInTheDocument();
});

test("question uses cross-topic endpoint, not current selection; duplicate sends blocked", async () => {
  const fetcher = vi.fn((_url: string, options?: RequestInit) => options?.method === "POST" ? response({ accepted: true }) : response({ turns: [], job: { status: "idle" } }));
  vi.stubGlobal("fetch", fetcher);
  render(<RealMailboxAsk open onClose={() => {}} onBusy={() => {}} onCitation={() => {}} />);
  await screen.findByText("从邮件往来中寻找答案");
  fireEvent.change(screen.getByLabelText("向邮箱提问"), { target: { value: "哪些询价？" } });
  fireEvent.click(screen.getByLabelText("发送问题"));
  await waitFor(() => expect(fetcher.mock.calls.some(([, o]) => o?.method === "POST")).toBe(true));
  const request = fetcher.mock.calls.find(([, o]) => o?.method === "POST")!;
  expect(request[0]).toBe("/__localmail/assistant");
  expect(JSON.parse(request[1]!.body as string)).toEqual({ question: "哪些询价？" });
});
