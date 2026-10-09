import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import App from "@/App";
import type { Thread } from "@/data/types";
import { threads } from "@/fixtures/threads";
import { countFolders, inFolder } from "./folders";
import { ThreadDetail } from "./thread-detail";
import { ThreadRow } from "./thread-row";
import { TipProvider } from "./tip";

const inquiry = threads.find(t => t.reading?.status === "ok" && t.reading.is_inquiry)!;
const oldOther = threads.find(t => t.folder === "invalid")!;
const newsletter: Thread = { ...oldOther, reading: oldOther.reading?.status === "ok"
  ? { ...oldOther.reading, mail_type: "newsletter" } : undefined };
const wrap = (node: React.ReactNode) => render(<MemoryRouter><TipProvider>{node}</TipProvider></MemoryRouter>);

afterEach(() => { localStorage.clear(); window.history.pushState({}, "", "/"); });

it("keeps ordinary mail readable and highlights only potential leads", () => {
  wrap(<><ThreadRow thread={newsletter} search="" /><ThreadRow thread={inquiry} search="" /></>);
  expect(screen.getByText("新闻订阅")).toBeInTheDocument();
  expect(screen.getByText("SALES LEAD")).toBeInTheDocument();
  expect(screen.queryByText("无效")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: new RegExp(newsletter.contact) })).not.toHaveClass("opacity-70");
});

it("separates sales progress, neutral mail types and the trash count", () => {
  const deleted = { ...inquiry, id: "deleted", deleted_at: "2026-10-03T00:00:00Z" };
  const counts = countFolders([{ ...inquiry, folder: "inbox" }, newsletter, deleted]);
  expect(counts).toMatchObject({ all: 2, leads: 1, inbox: 1, invalid: 1, trash: 1 });
  expect(inFolder(deleted, "leads")).toBe(false);
  expect(inFolder(newsletter, "inbox")).toBe(false);
  expect(inFolder({ ...newsletter, has_lead: true }, "leads")).toBe(true);
  wrap(<ThreadRow thread={oldOther} search="" />);
  expect(screen.getByText("其他邮件")).toBeInTheDocument();
});

it("respects explicit ordinary classifications and retains trade cues in title-only rows", () => {
  const ordinary: Thread = { ...inquiry, id: "ordinary", has_lead: false, has_trade: false,
    reading: inquiry.reading?.status === "ok" ? { ...inquiry.reading, is_trade: false, mail_type: "business", is_inquiry: false } : undefined };
  expect(inFolder(ordinary, "leads")).toBe(false);
  expect(inFolder({ ...ordinary, has_trade: true }, "leads")).toBe(true);
  wrap(<ThreadRow thread={inquiry} search="" compact />);
  expect(screen.getByLabelText("SALES LEAD")).toBeInTheDocument();
  expect(screen.getByText(inquiry.subject)).toBeInTheDocument();
  expect(screen.queryByText(inquiry.company)).not.toBeInTheDocument();
});

it("shows a warning instead of an ungrounded summary in the inbox preview", () => {
  const suspect = { ...inquiry, reading: inquiry.reading?.status === "ok" ? { ...inquiry.reading, summary_zh: "虚构 9999 台", unverified: ["9999"] } : undefined };
  wrap(<ThreadRow thread={suspect} search="" />);
  expect(screen.getByText("摘要中的数字未通过核对，请阅读原文。")).toBeInTheDocument();
  expect(screen.queryByText("虚构 9999 台")).not.toBeInTheDocument();
});

it("shows deletion failure and does not pretend the conversation was deleted", async () => {
  const organize = vi.fn().mockResolvedValue("不能访问这个邮箱");
  wrap(<ThreadDetail thread={newsletter} backSearch="" onOrganize={organize} />);
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("不能访问这个邮箱");
  expect(organize).toHaveBeenCalledWith("trash");
  expect(screen.getByRole("button", { name: "删除" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "恢复" })).not.toBeInTheDocument();
});

it("deletes a conversation into a visible recoverable trash and restores it", async () => {
  localStorage.setItem("mail2leads.user", "Larry");
  window.history.pushState({}, "", `/t/${oldOther.id}`);
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "主导航" });
  expect(within(nav).queryByText("无效")).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: "删除" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "恢复" })).toBeEnabled());
  expect(screen.getByRole("status")).toHaveTextContent("已移入 Aimail 回收站");
  if (nav.closest("[hidden]")) fireEvent.click(screen.getByRole("button", { name: "展开主导航" }));
  expect(within(nav).getByRole("link", { name: /回收站/ })).toHaveTextContent("1");
  fireEvent.click(within(nav).getByRole("link", { name: /回收站/ }));
  const row = await screen.findByRole("link", { name: new RegExp(oldOther.contact) });
  fireEvent.click(row);
  fireEvent.click(await screen.findByRole("button", { name: "恢复" }));
  if (nav.closest("[hidden]")) fireEvent.click(screen.getByRole("button", { name: "展开主导航" }));
  await waitFor(() => expect(within(nav).getByRole("link", { name: /回收站/ })).toHaveTextContent("0"));
  expect(screen.queryByText(/已移入 Aimail 回收站/)).not.toBeInTheDocument();
});
