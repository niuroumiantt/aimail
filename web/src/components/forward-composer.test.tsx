import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ForwardComposer } from "./forward-composer";
import { TipProvider } from "./tip";
import type { Thread } from "@/data/types";
import type { ReplyHandlers } from "./reply-composer";

const thread: Thread = {
  id: "10", subject: "RFQ", company: "Acme", contact: "Grace", email: "grace@example.test",
  region: "", scale: "", folder: "inbox", updated_at: "2026-10-10T10:00:00Z",
  messages: [{ id: "11", direction: "in", from_name: "Grace", from_email: "grace@example.test", sent_at: "2026-10-09T10:00:00Z", body: "First original", attachments: [{ id: "1", name: "spec.pdf", size: 12, read: "ok" }] },
    { id: "12", direction: "out", from_name: "Larry", from_email: "larry@example.test", sent_at: "2026-10-10T10:00:00Z", body: "Second original" }],
};
function show(send = vi.fn(async () => "")) {
  const reply: ReplyHandlers = { user: "Larry", onSetUser: vi.fn(), canDraft: true, latestDraft: vi.fn(), makeDraft: vi.fn(), send };
  const close = vi.fn();
  render(<TipProvider><ForwardComposer thread={thread} reply={reply} onClose={close} /></TipProvider>);
  return { reply, close };
}
it("opening a forward neither calls a model nor sends; recipients start empty", async () => {
  const { reply, close } = show();
  expect(screen.getByLabelText("收件人")).toHaveValue("");
  expect(screen.getByLabelText("主题")).toHaveValue("Fwd: RFQ");
  fireEvent.click(screen.getByRole("button", { name: "发送转发" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("有效的收件邮箱");
  expect(reply.send).not.toHaveBeenCalled();
  expect(reply.makeDraft).not.toHaveBeenCalled(); expect(reply.latestDraft).not.toHaveBeenCalled();
  expect(close).not.toHaveBeenCalled();
});
it("sends the explicitly selected original and attachment choice with an optional comment", async () => {
  const { reply, close } = show();
  fireEvent.change(screen.getByLabelText("收件人"), { target: { value: "buyer@example.test; partner@example.test" } });
  fireEvent.change(screen.getByLabelText("转发哪封邮件"), { target: { value: "11" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /包含原邮件附件/ }));
  fireEvent.click(screen.getByRole("button", { name: "发送转发" }));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  expect(reply.send).toHaveBeenCalledWith("10", { to: ["buyer@example.test", "partner@example.test"], subject: "Fwd: RFQ", body: "", forward_message_id: "11", include_attachments: false });
});
it("an uncertain send retains the draft and disables repeat clicks while pending", async () => {
  let finish!: (value: string) => void;
  const send = vi.fn(() => new Promise<string>(resolve => { finish = resolve; }));
  const { close } = show(send);
  fireEvent.change(screen.getByLabelText("收件人"), { target: { value: "buyer@example.test" } });
  fireEvent.click(screen.getByRole("button", { name: "发送转发" }));
  expect(screen.getByRole("button", { name: "正在发送…" })).toBeDisabled();
  finish("发送结果待核对，请检查已发送邮件，禁止自动重试");
  expect(await screen.findByRole("alert")).toHaveTextContent("禁止自动重试");
  expect(screen.getByLabelText("收件人")).toHaveValue("buyer@example.test");
  expect(send).toHaveBeenCalledTimes(1); expect(close).not.toHaveBeenCalled();
});
