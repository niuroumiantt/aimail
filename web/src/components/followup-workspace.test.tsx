import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { FollowupWorkspace } from "./followup-workspace";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks(); });

function show(unresolved = false, owner = "larry@example.test") {
  const state = { thread_id: 7, owner, pending: "", version: 2, summary: "{}", note: "" };
  let resolved = false;
  const fetcher = vi.fn(async (path: string, options?: RequestInit) => {
    if (path.endsWith("/resolve")) resolved = true;
    const value = path === "/api/followups" ? { identity: "larry@example.test", members: [], items: [] }
      : path.endsWith("/read") ? { ok: true }
      : { state, last_message_id: 19, unresolved_send: unresolved && !resolved ? { id: 1, sender: owner, state: "unknown", created_at: "2026-09-25" } : null,
        thread: { subject: "Customer RFQ", messages: [{ id: "19", from_email: "customer@example.test", sent_at: "2026-09-25", body: "Original request", quoted: null }] }, history: [] };
    void options;
    return new Response(JSON.stringify(value), { status: 200 });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/followups/7"]}><Routes><Route path="/followups/:id" element={<FollowupWorkspace />} /></Routes></MemoryRouter>);
  return fetcher;
}

it("keeps unresolved delivery blocked after loading persisted server state", async () => {
  const fetcher = show(true);
  expect(await screen.findByText("发送结果待核对，已暂停重复发送")).toBeInTheDocument();
  expect(screen.getByLabelText("回复正文")).toBeDisabled();
  expect(screen.getByRole("button", { name: "核对发件身份与内容" })).toBeDisabled();
  expect(screen.getByRole("link", { name: /下载待核对原邮件/ })).toHaveAttribute("href", "/api/followups/7/unresolved.eml");
  expect(fetcher.mock.calls.every(([path]) => !path.endsWith("/reply"))).toBe(true);
});

it("shows originals and marks only the displayed snapshot read after an explicit click", async () => {
  const fetcher = show();
  expect(await screen.findByText("Original request")).toBeInTheDocument();
  expect(fetcher.mock.calls.some(([path]) => path.endsWith("/read"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "将当前显示的邮件标为已读" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/followups/7/read", expect.objectContaining({ method: "POST", body: JSON.stringify({last_message_id:19}) })));
});

it("does not offer personal reply controls to a non-owner", async () => {
  show(false, "cloud@example.test");
  await screen.findByText("Original request");
  expect(screen.queryByLabelText("回复正文")).not.toBeInTheDocument();
});

it("refreshes unread reminders on the open list without syncing mail or sending", async () => {
  vi.useFakeTimers();
  let unread = 0;
  const fetcher = vi.fn(async (path: string) => {
    if (path !== "/api/followups") throw new Error(`Unexpected request: ${path}`);
    return new Response(JSON.stringify({
      identity: "larry@example.test",
      members: ["larry@example.test", "cloud@example.test"],
      items: [{ thread_id: 7, owner: "larry@example.test", pending: "", version: 1, summary: "{}", note: "", subject: "Customer RFQ", unread_count: unread }],
    }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/followups"]}><Routes><Route path="/followups" element={<FollowupWorkspace />} /></Routes></MemoryRouter>);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(screen.getByRole("status")).toHaveTextContent("无未读来信");
  fetcher.mockClear();
  unread = 2;
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledWith("/api/followups", expect.objectContaining({ method: "GET" }));
  expect(screen.getByRole("status")).toHaveTextContent("2 封未读来信");
  expect(fetcher.mock.calls.every(([path]) => path === "/api/followups")).toBe(true);
});

it("refreshes follow-up status when returning to the visible tab", async () => {
  let unread = 0;
  const fetcher = vi.fn(async (path: string) => {
    if (path !== "/api/followups") throw new Error(`Unexpected request: ${path}`);
    return new Response(JSON.stringify({
      identity: "larry@example.test",
      members: ["larry@example.test", "cloud@example.test"],
      items: [{ thread_id: 7, owner: "larry@example.test", pending: "", version: 1, summary: "{}", note: "", subject: "Customer RFQ", unread_count: unread }],
    }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetcher);
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  render(<MemoryRouter initialEntries={["/followups"]}><Routes><Route path="/followups" element={<FollowupWorkspace />} /></Routes></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("无未读来信"));
  fetcher.mockClear();
  unread = 1;
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status")).toHaveTextContent("1 封未读来信");
});

it("requires provider evidence and resolves without sending a message", async () => {
  const fetcher = show(true);
  expect(await screen.findByText("发送结果待核对，已暂停重复发送")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "记录核对结果（不发送邮件）" });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByLabelText("核对结果"), { target: { value: "not_sent" } });
  fireEvent.change(screen.getByLabelText("服务商核对依据"), { target: { value: "provider rejection 1234" } });
  fireEvent.click(submit);
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
    "/api/followups/7/unresolved/1/resolve",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ outcome: "not_sent", evidence_reference: "provider rejection 1234" }) }),
  ));
  expect(await screen.findByText("已根据服务商证据记录为未发送；系统没有重试。请人工检查内容后再决定是否新建发送。")).toBeInTheDocument();
  expect(fetcher.mock.calls.some(([path]) => path.endsWith("/reply"))).toBe(false);
});
