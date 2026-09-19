import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AttachmentText, Message } from "@/data/types";
import { MessageView } from "./message";
import { TipProvider } from "./tip";

const message: Message = {
  id: "m1",
  direction: "in",
  from_name: "Omar",
  from_email: "omar@gulfedge.example",
  sent_at: "2026-09-18T23:05:00+08:00",
  body: "Spec attached.",
  attachments: [
    { id: "a1", name: "spec.pdf", size: 184320, read: "ok" },
    { id: "a2", name: "scan.pdf", size: 2411520, read: "failed", reason: "PDF 没有文字层(扫描件),要走 vision 路由,还没接" },
  ],
};

const readsFine = async (id: string): Promise<AttachmentText> => ({
  id,
  name: "spec.pdf",
  status: "ok",
  text: "8x NVIDIA B300 SXM",
  reason: "",
});

const show = (impl: (id: string) => Promise<AttachmentText> = readsFine) => {
  const onAttachment = vi.fn(impl);
  render(
    <TipProvider>
      <MessageView message={message} onAttachment={onAttachment} />
    </TipProvider>,
  );
  return onAttachment;
};

it("marks an attachment that could not be read and says why", () => {
  show();
  const chips = screen.getAllByTestId("attachment");
  expect(chips[1]).toHaveAttribute("data-read", "failed");
  expect(chips[1]).toHaveAccessibleName(/没读出来.*vision/);
});

it("opens the text that was read out of an attachment", async () => {
  const onAttachment = show();
  fireEvent.click(screen.getAllByTestId("attachment")[0]);
  expect(await screen.findByTestId("attachment-text")).toHaveTextContent("8x NVIDIA B300 SXM");
  expect(onAttachment).toHaveBeenCalledWith("a1");
});

it("shows the reason instead of a blank sheet when the text is missing", async () => {
  show(async (id) => ({ id, name: "scan.pdf", status: "failed", text: "", reason: "PDF 没有文字层" }));
  fireEvent.click(screen.getAllByTestId("attachment")[1]);
  expect(await screen.findByRole("alert")).toHaveTextContent("PDF 没有文字层");
});

it("lists attachments without a way to open them when no handler is given", () => {
  render(
    <TipProvider>
      <MessageView message={message} />
    </TipProvider>,
  );
  expect(screen.getAllByTestId("attachment")[0]).toBeDisabled();
});
