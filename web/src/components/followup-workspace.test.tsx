import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { FollowupWorkspace } from "./followup-workspace";

afterEach(() => vi.unstubAllGlobals());

function show(unresolved = false, owner = "larry@example.test") {
  const state = { thread_id: 7, owner, pending: "", version: 2, summary: "{}", note: "" };
  const fetcher = vi.fn(async (path: string, options?: RequestInit) => {
    const value = path === "/api/followups" ? { identity: "larry@example.test", members: [], items: [] }
      : path.endsWith("/read") ? { ok: true }
      : { state, last_message_id: 19, unresolved_send: unresolved ? { id: 1, sender: owner, state: "unknown", created_at: "2026-09-25" } : null,
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
