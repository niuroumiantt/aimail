import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { threads } from "@/fixtures/threads";
import type { CustomerContext } from "@/data/types";
import { CustomerWorkspace } from "./customer-workspace";
import { ThreadList } from "./thread-list";
import { TipProvider } from "./tip";

const thread = threads[0];
const context: CustomerContext = { email: thread.email, configured: true, reason: "", projects: [{ id: thread.id, subject: "GPU 采购", updated_at: "2026-10-04", state: "ok", stale: false, error: "", scope: { total: 3, included: 3, truncated: 0, unread_attachments: 0 }, summary: { model: "测试模型", task_version: "ask_mailbox@1", produced_at: "2026-10-04T01:00:00Z", findings: [{ text: "当前需求为 2 台 H200", quote: "2 H200", source_id: 12, thread_id: Number(thread.id), subject: "GPU", unverified: [] }], scope: { total: 3, included: 3, truncated: 0, unread_attachments: 0 } }, messages: [{ id: "10", sent_at: "2026-10-01T01:00:00Z", direction: "in", from_email: thread.email, subject: "最初 4 台" }, { id: "12", sent_at: "2026-10-04T01:00:00Z", direction: "in", from_email: thread.email, subject: "最新 2 台" }] }] };
const wrap = (node: React.ReactNode) => <MemoryRouter><TipProvider>{node}</TipProvider></MemoryRouter>;

it("reuses the latest customer snapshot while switching historical mail and retains source links", async () => {
  const load = vi.fn().mockResolvedValue(context);
  const refresh = vi.fn().mockResolvedValue({ queued: 0 });
  const props = { thread, mailbox: "sales@test", revision: "same", load, refresh, onAnalyze: vi.fn() };
  const view = render(wrap(<CustomerWorkspace {...props} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看原文来源" })).toHaveAttribute("href", `/t/${thread.id}#mail-12`);
  view.rerender(wrap(<CustomerWorkspace {...props} thread={{ ...thread, subject: "最初 4 台" }} />));
  expect(screen.getByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(refresh).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "更新客户需求摘要" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledWith(thread.id, true));
});

it("cannot show an earlier mailbox's customer snapshot while the next mailbox is loading", async () => {
  const load = vi.fn().mockResolvedValueOnce(context).mockResolvedValueOnce(context);
  const props = { thread, mailbox: "first@test", revision: "same", load, refresh: vi.fn(), onAnalyze: vi.fn() };
  const view = render(wrap(<CustomerWorkspace {...props} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  load.mockImplementation(() => new Promise(() => {}));
  view.rerender(wrap(<CustomerWorkspace {...props} mailbox="second@test" />));
  expect(screen.queryByText("当前需求为 2 台 H200")).not.toBeInTheDocument();
});

it("shows stale and failed state ahead of prior results and refuses ungrounded numbers silently", async () => {
  const stale = { ...context, projects: [{ ...context.projects[0], state: "failed" as const, stale: true, error: "更新失败", summary: { ...context.projects[0].summary!, findings: [{ ...context.projects[0].summary!.findings[0], unverified: ["999"] }] } }] };
  const refresh = vi.fn();
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="same" load={vi.fn().mockResolvedValue(stale)} refresh={refresh} onAnalyze={vi.fn()} />));
  expect(await screen.findByText("有新内容，以下仍为上一次成功摘要。")).toBeInTheDocument();
  expect(screen.getAllByRole("alert").map(item => item.textContent).join(" ")).toContain("999");
  expect(refresh).not.toHaveBeenCalled();
});

it("groups exact contacts without merging separate topics and supports working search and both densities", () => {
  localStorage.clear();
  const other = { ...thread, id: "different", subject: "独立存储采购" };
  render(wrap(<ThreadList threads={[thread, other]} folder="all" search="" />));
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  const group = screen.getByRole("button", { name: new RegExp(thread.contact) });
  expect(group).toHaveTextContent("2 个话题");
  expect(screen.getByRole("link", { name: /独立存储采购/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "简洁" }));
  expect(screen.getByRole("link", { name: /独立存储采购/ })).toHaveClass("mail-thread-compact");
  fireEvent.click(screen.getByRole("button", { name: "概括" }));
  expect(screen.getByRole("link", { name: /独立存储采购/ })).not.toHaveClass("mail-thread-compact");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "独立存储" } });
  expect(within(screen.getByRole("button", { name: new RegExp(thread.contact) })).getByText("1 个话题")).toBeInTheDocument();
  fireEvent.click(group);
  expect(screen.queryByRole("link", { name: /独立存储采购/ })).not.toBeInTheDocument();
  localStorage.clear();
});
