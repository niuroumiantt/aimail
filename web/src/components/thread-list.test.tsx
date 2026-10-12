import { fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { threads } from "@/fixtures/threads";
import { dateGroup, ThreadList } from "./thread-list";
import { TipProvider } from "./tip";

afterEach(() => { localStorage.clear(); vi.useRealTimers(); });

it("warns before deleting only the visible contact group, including collapsed groups", async () => {
  const first = { ...threads[0], message_count: 3 };
  const second = { ...first, id: "second", subject: "Second", message_count: 2 };
  const other = { ...first, id: "other", email: "different@example.test", contact: "Different" };
  const remove = vi.fn().mockResolvedValue("");
  render(<MemoryRouter><TipProvider><ThreadList threads={[first, second, other]} folder="all" search="" onTrashGroup={remove} /></TipProvider></MemoryRouter>);
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${first.contact}`) }));
  fireEvent.click(screen.getByRole("button", { name: `整组删除 ${first.contact}` }));
  expect(screen.getByRole("dialog")).toHaveTextContent("⚠️");
  expect(screen.getByRole("dialog")).toHaveTextContent("2 个话题，共 5 封邮件");
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: `整组删除 ${first.contact}` }));
  fireEvent.click(screen.getByRole("button", { name: "确认移入回收站" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(remove).toHaveBeenCalledExactlyOnceWith({ email: first.email, threads: [
    { id: first.id, updated_at: first.updated_at, message_count: 3 },
    { id: second.id, updated_at: second.updated_at, message_count: 2 },
  ] });
});

it("keeps failed deletion visible and offers no bulk deletion from trash", async () => {
  const remove = vi.fn().mockResolvedValue("邮件已有更新");
  const view = render(<MemoryRouter><ThreadList threads={[threads[0]]} folder="all" search="" onTrashGroup={remove} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  fireEvent.click(screen.getByRole("button", { name: `整组删除 ${threads[0].contact}` }));
  fireEvent.click(screen.getByRole("button", { name: "确认移入回收站" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("邮件已有更新");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  view.rerender(<MemoryRouter><ThreadList threads={[threads[0]]} folder="trash" search="" onTrashGroup={remove} /></MemoryRouter>);
  expect(screen.queryByRole("button", { name: /^整组删除/ })).not.toBeInTheDocument();
});

it("shows concise Chinese descriptions with unchanged English senders and preserves the normal view", async () => {
  const thread = { ...threads[0], subject: "Your latest statement is available", contact: "Chase" };
  const load = vi.fn().mockResolvedValue({ [thread.id]: { status: "ok", text_zh: "银行月结单通知", reason: "", model: "test", task_version: "list_caption@1", produced_at: "2026-10-12" } });
  render(<MemoryRouter><TipProvider><ThreadList threads={[thread]} folder="all" search="" loadCaptions={load} /></TipProvider></MemoryRouter>);
  expect(screen.getByText(thread.subject)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "简洁" }));
  await screen.findByText("银行月结单通知");
  const link = screen.getByTitle(thread.subject).closest("a")!;
  expect(link).toHaveClass("mail-thread-compact");
  expect(within(link).getByText("Chase")).toBeInTheDocument();
  expect(thread.subject).toBe("Your latest statement is available");
  fireEvent.click(screen.getByRole("button", { name: "概括" }));
  expect(screen.getByText(thread.subject)).toBeInTheDocument();
});

it("groups by local calendar days and starts the week on Monday", () => {
  const now = new Date(2026, 9, 9, 12);
  expect(dateGroup(new Date(2026, 9, 9, 0).toISOString(), now)).toBe("今天");
  expect(dateGroup(new Date(2026, 9, 8, 23).toISOString(), now)).toBe("昨天");
  expect(dateGroup(new Date(2026, 9, 5, 9).toISOString(), now)).toBe("本周");
  expect(dateGroup(new Date(2026, 9, 4, 23).toISOString(), now)).toBe("更早");
  expect(dateGroup("invalid", now)).toBe("日期未知");
  expect(dateGroup(new Date(2026, 9, 10).toISOString(), now)).toBe("日期未知");
  expect(dateGroup(new Date(2026, 9, 11).toISOString(), new Date(2026, 9, 12, 12))).toBe("昨天");
});

it("uses the header search without a second search box and preserves matching topic links", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date(2026, 9, 9, 12));
  const today = { ...threads[0], updated_at: new Date(2026, 9, 9, 9).toISOString(), company: "gmail" };
  const yesterday = { ...threads[1], updated_at: new Date(2026, 9, 8, 18).toISOString() };
  const view = render(<MemoryRouter><TipProvider><ThreadList threads={[today, yesterday]} folder="all" search="" query="" /></TipProvider></MemoryRouter>);
  expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "今天" })).getByRole("link")).toHaveTextContent(today.contact);
  expect(screen.queryByText("gmail")).not.toBeInTheDocument();
  view.rerender(<MemoryRouter><TipProvider><ThreadList threads={[today, yesterday]} folder="all" search="" query={yesterday.subject} /></TipProvider></MemoryRouter>);
  expect(screen.queryByRole("region", { name: "今天" })).not.toBeInTheDocument();
  expect(screen.getByRole("link")).toHaveTextContent(yesterday.subject);
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  expect(screen.getByRole("button", { name: new RegExp(yesterday.contact) })).toHaveTextContent("1 个话题");
});
