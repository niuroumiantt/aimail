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

it("keeps the selected topic's latest overview when reading historical mail and removes source clutter", async () => {
  const load = vi.fn().mockResolvedValue(context);
  const refresh = vi.fn().mockResolvedValue({ queued: 0 });
  const props = { thread, mailbox: "sales@test", revision: "same", load, refresh };
  const view = render(wrap(<CustomerWorkspace {...props} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByText("当前邮件的单封读数")).not.toBeInTheDocument();
  expect(screen.queryByText("往来与变化来源")).not.toBeInTheDocument();
  expect(screen.getByText("3 封往来 · 来信与我方回复")).toBeInTheDocument();
  expect(screen.getByText(/测试模型/)).toHaveTextContent("ask_mailbox@1");
  view.rerender(wrap(<CustomerWorkspace {...props} thread={{ ...thread, subject: "最初 4 台" }} />));
  expect(screen.getByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(refresh).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "更新当前话题的生意概况" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledWith(thread.id, true));
});

it("cannot show an earlier mailbox's customer snapshot while the next mailbox is loading", async () => {
  const load = vi.fn().mockResolvedValueOnce(context).mockResolvedValueOnce(context);
  const props = { thread, mailbox: "first@test", revision: "same", load, refresh: vi.fn() };
  const view = render(wrap(<CustomerWorkspace {...props} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  load.mockImplementation(() => new Promise(() => {}));
  view.rerender(wrap(<CustomerWorkspace {...props} mailbox="second@test" />));
  expect(screen.queryByText("当前需求为 2 台 H200")).not.toBeInTheDocument();
});

it("shows stale and failed state ahead of prior results and refuses ungrounded numbers silently", async () => {
  const stale = { ...context, projects: [{ ...context.projects[0], state: "failed" as const, stale: true, error: "更新失败", summary: { ...context.projects[0].summary!, findings: [{ ...context.projects[0].summary!.findings[0], unverified: ["999"] }] } }] };
  const refresh = vi.fn();
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="same" load={vi.fn().mockResolvedValue(stale)} refresh={refresh} />));
  expect(await screen.findByText("有新内容，以下仍为上一次成功概况。")).toBeInTheDocument();
  expect(screen.getAllByRole("alert").map(item => item.textContent).join(" ")).toContain("999");
  expect(refresh).not.toHaveBeenCalled();
});

it("isolates the selected business topic without refreshing unrelated unprocessed projects", async () => {
  const unrelated = { ...context.projects[0], id: "another-topic", subject: "独立存储采购", state: "none" as const, stale: true, summary: null };
  const load = vi.fn().mockResolvedValue({ ...context, projects: [unrelated, context.projects[0]] });
  const refresh = vi.fn();
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="same" load={load} refresh={refresh} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(screen.queryByText("独立存储采购")).not.toBeInTheDocument();
  expect(refresh).not.toHaveBeenCalled();
  expect(load).toHaveBeenCalledTimes(1);
});

it("does not show the prior topic's overview while another topic from the same sender loads", async () => {
  const load = vi.fn().mockResolvedValue(context);
  const props = { thread, mailbox: "test", revision: "same", load, refresh: vi.fn() };
  const view = render(wrap(<CustomerWorkspace {...props} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  load.mockImplementation(() => new Promise(() => {}));
  view.rerender(wrap(<CustomerWorkspace {...props} thread={{ ...thread, id: "new-topic", subject: "独立存储采购" }} />));
  expect(screen.queryByText("当前需求为 2 台 H200")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "独立存储采购" })).toBeInTheDocument();
});

it("refreshes only the selected stale topic once before showing its newest unified overview", async () => {
  const stale = { ...context, projects: [{ ...context.projects[0], stale: true, state: "none" as const }] };
  const load = vi.fn().mockResolvedValueOnce(stale).mockResolvedValue(context);
  const refresh = vi.fn().mockResolvedValue({ queued: 1 });
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="new-mail" load={load} refresh={refresh} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  await waitFor(() => expect(refresh).toHaveBeenCalledWith(thread.id, false));
  expect(refresh).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(screen.queryByText("有新内容，以下仍为上一次成功概况。")).not.toBeInTheDocument());
});

it("retains cached overview and its model attribution when the selected model is unavailable", async () => {
  const refresh = vi.fn();
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="same" load={vi.fn().mockResolvedValue({ ...context, configured: false })} refresh={refresh} />));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(screen.getByText("模型暂不可用，已保存的概况仍可查看。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "更新当前话题的生意概况" })).toBeDisabled();
  expect(screen.getByText(/测试模型/)).toHaveTextContent("ask_mailbox@1");
  expect(refresh).not.toHaveBeenCalled();
});

it("lets a failed context read recover without generating an unchanged overview", async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error("读取失败")).mockResolvedValue(context);
  const refresh = vi.fn();
  render(wrap(<CustomerWorkspace thread={thread} mailbox="test" revision="same" load={load} refresh={refresh} />));
  expect(await screen.findByRole("alert")).toHaveTextContent("读取失败");
  fireEvent.click(screen.getByRole("button", { name: "更新当前话题的生意概况" }));
  expect(await screen.findByText("当前需求为 2 台 H200")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(refresh).toHaveBeenCalledWith(thread.id, true);
});

it("labels an email domain honestly without presenting the legacy company placeholder as a company", async () => {
  render(wrap(<CustomerWorkspace thread={{ ...thread, company: "gmail", email: "buyer@gmail.com", region: "" }} mailbox="test" revision="same" load={vi.fn().mockResolvedValue(context)} refresh={vi.fn()} />));
  expect(screen.getByText("邮箱域名")).toBeInTheDocument();
  expect(screen.getByText("gmail.com")).toBeInTheDocument();
  expect(screen.queryByText("gmail", { exact: true })).not.toBeInTheDocument();
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
