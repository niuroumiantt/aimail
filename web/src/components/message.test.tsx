import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AttachmentText, Message, MessageTranslation } from "@/data/types";
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

const translated: MessageTranslation = {
  status: "ok",
  text_zh: "规格见附件。请报价 4 台 L40S。",
  model: "Codex CLI · gpt-6.1-sol",
  task_version: "translate_mail@1",
  produced_at: "2026-10-04T13:30:00Z",
  reason: "",
  coverage: "当前邮件新增正文；不含折叠的引用历史与附件",
};

it("translates only on an explicit click and changes views without more model calls", async () => {
  const get = vi.fn(async () => null);
  const translate = vi.fn(async () => translated);
  const withQuoted = { ...message, quoted: "Earlier price USD 500." };
  render(<TipProvider><MessageView message={withQuoted} onGetTranslation={get} onTranslate={translate} /></TipProvider>);
  expect(get).not.toHaveBeenCalled();
  expect(translate).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByText(translated.text_zh)).toBeVisible();
  expect(screen.getByLabelText("邮件原文")).not.toBeVisible();
  expect(screen.getByRole("button", { name: "中文" })).toHaveAttribute("aria-pressed", "true");
  expect(get).toHaveBeenCalledExactlyOnceWith("m1");
  expect(translate).toHaveBeenCalledExactlyOnceWith("m1");
  expect(screen.getByText(/Codex CLI · gpt-6.1-sol/)).toBeVisible();
  expect(screen.getByText("邮件 #m1")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "对照" }));
  expect(screen.getByLabelText("邮件原文")).toBeVisible();
  expect(screen.getByLabelText("中文译文")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "原文" }));
  expect(screen.getByLabelText("中文译文")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /展开引用历史/ }));
  expect(screen.getByText("Earlier price USD 500.")).toBeVisible();
  expect(screen.getAllByTestId("attachment")).toHaveLength(2);
  expect(translate).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledTimes(1);
});

it("reuses a cached translation and keeps its attribution when the selected model changes", async () => {
  const get = vi.fn(async () => translated);
  const translate = vi.fn(async () => translated);
  const { rerender } = render(<MessageView message={message} onGetTranslation={get} onTranslate={translate} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByText(translated.text_zh)).toBeVisible();
  expect(translate).not.toHaveBeenCalled();
  const otherModel = vi.fn(async () => ({ ...translated, model: "Spark · fast" }));
  rerender(<MessageView message={message} onGetTranslation={get} onTranslate={otherModel} />);
  fireEvent.click(screen.getByRole("button", { name: "对照" }));
  fireEvent.click(screen.getByRole("button", { name: "中文" }));
  expect(screen.getByText(/Codex CLI · gpt-6.1-sol/)).toBeVisible();
  expect(get).toHaveBeenCalledTimes(1);
  expect(otherModel).not.toHaveBeenCalled();
});

it("preserves the original and requires an explicit retry when a cache request fails", async () => {
  const get = vi.fn<() => Promise<MessageTranslation | null>>()
    .mockRejectedValueOnce(new Error("sensitive upstream failure"))
    .mockResolvedValueOnce(null);
  const translate = vi.fn(async () => translated);
  render(<MessageView message={message} onGetTranslation={get} onTranslate={translate} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("翻译暂不可用，请重试。原文仍可阅读。");
  expect(screen.queryByText(/sensitive upstream/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("邮件原文")).toBeVisible();
  expect(translate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重试翻译" }));
  expect(await screen.findByText(translated.text_zh)).toBeVisible();
  expect(translate).toHaveBeenCalledTimes(1);
});

it("keeps the original readable while translating and rejects duplicate clicks", async () => {
  let finish: (value: MessageTranslation) => void = () => undefined;
  const translate = vi.fn(() => new Promise<MessageTranslation>(resolve => { finish = resolve; }));
  render(<MessageView message={message} onGetTranslation={async () => null} onTranslate={translate} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  const busy = await screen.findByRole("button", { name: "正在翻译…" });
  expect(busy).toBeDisabled();
  expect(screen.getByLabelText("邮件原文")).toBeVisible();
  fireEvent.click(busy);
  expect(translate).toHaveBeenCalledTimes(1);
  finish(translated);
  expect(await screen.findByText(translated.text_zh)).toBeVisible();
});

it("does not show a translation from an earlier body after the message content changes", async () => {
  const get = vi.fn(async () => translated);
  const translate = vi.fn(async () => translated);
  const { rerender } = render(<MessageView message={message} onGetTranslation={get} onTranslate={translate} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByText(translated.text_zh)).toBeVisible();
  rerender(<MessageView message={{ ...message, body: "Revised quantity: 2 L40S." }} onGetTranslation={get} onTranslate={translate} />);
  expect(screen.queryByText(translated.text_zh)).not.toBeInTheDocument();
  expect(screen.getByText("Revised quantity: 2 L40S.")).toBeVisible();
  expect(screen.getByRole("button", { name: "翻译为中文" })).toBeEnabled();
  expect(get).toHaveBeenCalledTimes(1);
  expect(translate).not.toHaveBeenCalled();
});

it("shows failed translations clearly and renders translation content as plain text", async () => {
  const unsafeLooking = "<img src=x onerror=alert(1)>";
  const translate = vi.fn<() => Promise<MessageTranslation>>()
    .mockResolvedValueOnce({ ...translated, status: "failed", text_zh: "", reason: "翻译未通过数字核对，请重试。" })
    .mockResolvedValueOnce({ ...translated, text_zh: unsafeLooking });
  const { container } = render(<MessageView message={message} onGetTranslation={async () => null} onTranslate={translate} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("翻译未通过数字核对，请重试。");
  expect(screen.getByLabelText("邮件原文")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "重试翻译" }));
  expect(await screen.findByText(unsafeLooking)).toBeVisible();
  expect(container.querySelector("img")).toBeNull();
  await waitFor(() => expect(translate).toHaveBeenCalledTimes(2));
});

it("shows original HTML in an isolated frame without duplicating quoted history", () => {
  render(<TipProvider><MessageView message={{ ...message, body_html: '<p>Exact sender HTML</p><blockquote>Original quote</blockquote>', quoted: 'Original quote' }} /></TipProvider>);
  const frame = screen.getByTitle("客户原始邮件");
  expect(frame).toHaveAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
  expect(frame.getAttribute("srcdoc")).toContain("Exact sender HTML");
  expect(frame.getAttribute("srcdoc")).toContain("<blockquote>Original quote</blockquote>");
  expect(screen.queryByRole("button", { name: /展开引用历史/ })).toBeNull();
  expect(screen.queryByText(message.body)).toBeNull();
});

it("keeps original plain-text line breaks when HTML is unavailable", () => {
  const text = 'Part K4-123\n10 units\n\nUSD 25';
  render(<TipProvider><MessageView message={{ ...message, body: text, body_html: null, original_notice: 'HTML 正文过大，当前显示纯文本。' }} /></TipProvider>);
  expect(screen.queryByTitle("客户原始邮件")).toBeNull();
  expect(screen.getByLabelText("邮件原文").textContent).toContain(text);
  expect(screen.getByText('HTML 正文过大，当前显示纯文本。')).toBeVisible();
});

it("external image opt-in is limited to the selected original message", () => {
  const html = '<p>Hello</p><img src="https://example.test/logo">';
  const { rerender } = render(<TipProvider><MessageView message={{ ...message, body_html: html }} /></TipProvider>);
  fireEvent.click(screen.getByRole('button', { name: '加载本封外部图片' }));
  expect(screen.getByTitle('客户原始邮件').getAttribute('srcdoc')).toContain('src="https://example.test/logo"');
  rerender(<TipProvider><MessageView message={{ ...message, id: 'another', body_html: html }} /></TipProvider>);
  expect(screen.getByRole('button', { name: '加载本封外部图片' })).toBeVisible();
  expect(screen.getByTitle('客户原始邮件').getAttribute('srcdoc')).not.toContain('src="https://example.test/logo"');
});


it("explains a disconnected selected model without exposing arbitrary upstream errors", async () => {
  render(<MessageView message={message} onTranslate={vi.fn().mockRejectedValue(new Error("所选模型暂不可用，仍可阅读原文与已保存的译文。"))} />, { wrapper: TipProvider });
  fireEvent.click(screen.getByRole("button", { name: "翻译为中文" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("当前翻译模型未连接，请点击顶栏的模型图标检查连接状态");
  expect(screen.getByLabelText("邮件原文")).toBeVisible();
});

it("previews a scanned PDF as the original file and releases its download URL on close", async () => {
  const create = vi.fn(() => "blob:original-pdf");
  const revoke = vi.fn();
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = create;
    static revokeObjectURL = revoke;
  });
  const blob = new Blob(["%PDF-1.7 scanned original"], { type: "application/pdf" });
  const load = vi.fn(async () => blob);
  const text = vi.fn(readsFine);
  const view = render(<TipProvider><MessageView message={message} onAttachment={text} onAttachmentFile={load} /></TipProvider>);
  fireEvent.click(screen.getAllByTestId("attachment")[1]);
  expect(await screen.findByTitle("PDF 原件预览")).toHaveAttribute("src", "blob:original-pdf#view=FitH");
  expect(load).toHaveBeenCalledExactlyOnceWith("a2");
  expect(create).toHaveBeenCalledExactlyOnceWith(blob);
  expect(text).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "下载原件" })).toHaveAttribute("download", "scan.pdf");
  fireEvent.click(screen.getByRole("button", { name: "关闭附件预览" }));
  await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:original-pdf"));
  view.unmount();vi.unstubAllGlobals();
});

it("does not reopen an attachment or retain bytes if it finishes after closing", async () => {
  let finish!: (file: Blob) => void;
  const load = vi.fn(() => new Promise<Blob>(resolve => { finish = resolve; }));
  const create = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
  const view = render(<TipProvider><MessageView message={message} onAttachmentFile={load} /></TipProvider>);
  fireEvent.click(screen.getAllByTestId("attachment")[0]);
  fireEvent.click(screen.getByRole("button", { name: "关闭附件预览" }));
  finish(new Blob(["%PDF-1.7"], { type: "application/pdf" }));
  await waitFor(() => expect(screen.queryByTitle("PDF 原件预览")).toBeNull());
  expect(create).not.toHaveBeenCalled();
  view.unmount();vi.unstubAllGlobals();
});
