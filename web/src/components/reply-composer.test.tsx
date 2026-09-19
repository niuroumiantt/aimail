import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ReplyDraft, Thread } from "@/data/types";
import { ReplyComposer, sendProblem, type ReplyHandlers } from "./reply-composer";
import { TipProvider } from "./tip";

const thread: Thread = {
  id: "t1",
  subject: "RFQ 2U",
  company: "Aurora",
  contact: "Mikko Laine",
  email: "mikko@aurora.test",
  region: "",
  scale: "",
  folder: "inbox",
  updated_at: "2026-09-19T08:00:00+08:00",
  messages: [],
};

const signed = { model: "Spark · fast", task_version: "draft_reply@1", produced_at: "2026-09-19T08:01:00+08:00" };

const okDraft: ReplyDraft = {
  ...signed,
  id: "d1",
  status: "ok",
  language: "en",
  subject: "Re: RFQ 2U",
  body: "Thanks for asking about 480 units.\n\n[姓名]",
  open_questions: ["delivery address"],
  quoted_numbers: ["480"],
  unverified: ["480"],
};

function show(over: Partial<ReplyHandlers> = {}, user = "Larry") {
  const reply: ReplyHandlers = {
    user,
    onSetUser: vi.fn(),
    latestDraft: async () => null,
    makeDraft: async () => okDraft,
    send: vi.fn(async () => ""),
    ...over,
  };
  const onClose = vi.fn();
  render(
    <TipProvider>
      <ReplyComposer thread={thread} reply={reply} onClose={onClose} />
    </TipProvider>,
  );
  return { reply, onClose };
}

const body = () => screen.getByLabelText("正文") as HTMLTextAreaElement;

it("refuses to send while the name placeholder is still in the body", async () => {
  const { reply } = show();
  fireEvent.click(screen.getByRole("button", { name: "AI 起草" }));
  await waitFor(() => expect(body().value).toContain("[姓名]"));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText(/\[姓名\] 占位/)).toBeInTheDocument();
  expect(reply.send).not.toHaveBeenCalled();
});

it("shows who drafted and which numbers are unverified before anyone sends", async () => {
  show();
  fireEvent.click(screen.getByRole("button", { name: "AI 起草" }));
  expect(await screen.findByTestId("attribution")).toHaveTextContent("draft_reply@1");
  expect(screen.getByText(/发之前先核对/).parentElement).toHaveTextContent("480");
  expect(screen.getByText(/草稿向客户问了/)).toHaveTextContent("delivery address");
});

it("shows the failure instead of an empty draft", async () => {
  show({ makeDraft: async () => ({ ...signed, id: "d2", status: "failed", reason: "no json" }) });
  fireEvent.click(screen.getByRole("button", { name: "AI 起草" }));
  expect(await screen.findByTestId("draft-failed")).toHaveTextContent("no json");
  expect(body().value).toBe("");
});

it("sends only what the person wrote through their handler and then closes", async () => {
  const { reply, onClose } = show();
  fireEvent.change(body(), { target: { value: "Hello Mikko" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(reply.send).toHaveBeenCalledWith("t1", {
    to: ["mikko@aurora.test"],
    subject: "Re: RFQ 2U",
    body: "Hello Mikko",
  });
});

it("keeps the composer open and shows the reason when the server refuses", async () => {
  const { onClose } = show({ send: async () => "没有配置 SMTP,发不了" });
  fireEvent.change(body(), { target: { value: "Hello" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText("没有配置 SMTP,发不了")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

it("asks for a name before drafting or sending", () => {
  show({}, "");
  expect(screen.getByPlaceholderText("例如 Larry")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "AI 起草" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
});

it("restores the latest stored draft when reopened", async () => {
  show({ latestDraft: async () => okDraft });
  await waitFor(() => expect(body().value).toContain("480 units"));
  expect(screen.getByTestId("attribution")).toHaveTextContent("Spark · fast");
});

it("decides the hard rules in code before anything reaches the server", () => {
  expect(sendProblem({ to: [], subject: "", body: "x" })).toMatch(/收件人/);
  expect(sendProblem({ to: ["a@b.test"], subject: "", body: "  " })).toMatch(/空/);
  expect(sendProblem({ to: ["a@b.test"], subject: "", body: "hi [姓名]" })).toMatch(/占位/);
  expect(sendProblem({ to: ["a@b.test"], subject: "", body: "hi" })).toBe("");
});
