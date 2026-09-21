import { fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { MailboxAssistant } from "./mailbox-assistant";
import { recordDesignAudit } from "@/lib/design-audit";
vi.mock("@/lib/design-audit", () => ({ recordDesignAudit: vi.fn().mockResolvedValue(undefined) }));

beforeAll(() => {
  // jsdom has no layout or scrolling API; browser verification covers scrolling.
  Element.prototype.scrollIntoView = vi.fn();
});

const examples = [
  { company: "Aurora", subject: "Servers", body: "Change from 48 to 32 units.", request: "Quote please.", product: "2U", model: "X1", quantity: "32", old: "48", unit: "台", contact: "Mikko" },
  { company: "Gulf", subject: "GPUs", body: "Four H200 servers please.", request: "Quote please.", product: "H200", model: "H200", quantity: "4", old: "", unit: "台", contact: "Omar" },
];

describe("global mailbox assistant prototype", () => {
  it("clears only the display after saving and can restore the conversation", async () => {
    render(<MailboxAssistant open examples={examples} selected={0} confirmed={[]} onClose={vi.fn()} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /找出所有询价邮件/ }));
    fireEvent.click(screen.getByRole("button", { name: "清空当前显示" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "查看来源：Gulf" })).not.toBeInTheDocument());
    expect(recordDesignAudit).toHaveBeenCalledWith("assistant.clear_display", expect.objectContaining({ turns: expect.arrayContaining([expect.objectContaining({ question: "找出所有询价邮件" })]) }));
    fireEvent.click(screen.getByRole("button", { name: "查看已清屏的对话" }));
    expect(screen.getByRole("button", { name: "查看来源：Gulf" })).toBeInTheDocument();
  });

  it("retains the display when audit storage fails", async () => {
    render(<MailboxAssistant open examples={examples} selected={0} confirmed={[]} onClose={vi.fn()} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /找出所有询价邮件/ }));
    vi.mocked(recordDesignAudit).mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "清空当前显示" }));
    await screen.findByText("记录写入失败，未清屏。请重试。");
    expect(screen.getByRole("button", { name: "查看来源：Gulf" })).toBeInTheDocument();
  });
  it("searches all example mail independently of the selected thread and preserves citations after navigation", () => {
    const onNavigate = vi.fn();
    const props = { open: true, examples, selected: 0, confirmed: [], onClose: vi.fn(), onNavigate };
    const { rerender } = render(<MailboxAssistant {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /找出所有询价邮件/ }));
    expect(screen.getByRole("button", { name: "查看来源：Gulf" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看来源：Gulf" }));
    expect(onNavigate).toHaveBeenCalledWith(1);
    rerender(<MailboxAssistant {...props} selected={1} />);
    expect(screen.getByRole("button", { name: "查看来源：Aurora" })).toBeInTheDocument();
    expect(screen.getByText(/全部邮箱 · 1 个示例邮箱 · 2 条询盘/)).toBeInTheDocument();
  });

  it("freezes each answer scope and honestly distinguishes keyword misses from model answers", () => {
    const props = { open: true, examples, selected: 0, confirmed: [], onClose: vi.fn(), onNavigate: vi.fn() };
    const { rerender } = render(<MailboxAssistant {...props} />);
    fireEvent.change(screen.getByLabelText("阅读范围"), { target: { value: "current" } });
    fireEvent.click(screen.getByRole("button", { name: /找出所有询价邮件/ }));
    expect(screen.queryByRole("button", { name: "查看来源：Gulf" })).not.toBeInTheDocument();
    rerender(<MailboxAssistant {...props} selected={1} />);
    expect(screen.getByText("仅此询盘 · Aurora")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("向邮箱提问"), { target: { value: "calculate revenue" } });
    fireEvent.click(screen.getByRole("button", { name: "提交邮箱问题" }));
    expect(screen.getByText(/尚未接入自然语言分析/)).toBeInTheDocument();
    const turns = document.querySelectorAll(".ds-assistant-turn");
    expect(within(turns[1] as HTMLElement).queryByRole("button", { name: /查看来源/ })).not.toBeInTheDocument();
  });
});
