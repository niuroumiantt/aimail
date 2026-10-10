import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import type { FolderController } from "@/data/mail-folders";
import { threads } from "@/fixtures/threads";
import { MAIL_DRAG_TYPE, startMailDrag } from "@/lib/mail-drag";
import { MailFolderTree } from "./mail-folder-tree";
import { ThreadList } from "./thread-list";
import { TipProvider } from "./tip";

const scope = JSON.stringify(["sales@example.com", "Larry"]);
function transfer() {
  const values = new Map<string, string>();
  return { get types() { return [...values.keys()]; }, effectAllowed: "all", dropEffect: "none", clearData: () => values.clear(), setData: (type: string, value: string) => values.set(type, value), getData: (type: string) => values.get(type) ?? "" } as unknown as DataTransfer;
}
function makeController(): FolderController {
  return { data: { items: [{ id: "1", parent_id: null, name: "客户", count: 0 }, { id: "2", parent_id: "1", name: "亚洲", count: 0 }, { id: "3", parent_id: "2", name: "新加坡", count: 0 }], assignments: {} }, busy: false, enabled: true, error: "", command: vi.fn(async () => "") };
}
function Location() { const location = useLocation(); return <span aria-label="当前地址">{location.pathname}{location.search}</span>; }
function mount(c: FolderController) {
  return render(<MemoryRouter initialEntries={["/t/active"]}><TipProvider>
    <ThreadList threads={[threads[0]]} search="" folder="all" dragScope={scope} />
    <MailFolderTree controller={c} dragScope={scope} /><Location />
  </TipProvider></MemoryRouter>);
}
afterEach(() => localStorage.clear());

it.each([false, true])("drags a conversation from the %s grouped list to a third-level folder without navigating or exporting its URL", async grouped => {
  localStorage.setItem("aimail-list-preferences", JSON.stringify({ grouped, compact: grouped }));
  const c = makeController(); mount(c);
  const row = screen.getByRole("link", { name: new RegExp(threads[0].subject.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  const destination = screen.getByRole("link", { name: "新加坡" }).parentElement!;
  const data = transfer(); data.setData("text/uri-list", "https://mail.example.com/t/active");
  expect(row).toHaveAttribute("draggable", "true");
  fireEvent.dragStart(row, { dataTransfer: data });
  expect(data.types).toEqual([MAIL_DRAG_TYPE]); expect(data.effectAllowed).toBe("move");
  expect(c.command).not.toHaveBeenCalled();
  fireEvent.dragOver(destination, { dataTransfer: data });
  expect(destination).toHaveAttribute("data-drop-target", "true"); expect(data.dropEffect).toBe("move");
  fireEvent.drop(destination, { dataTransfer: data });
  await waitFor(() => expect(c.command).toHaveBeenCalledWith({ action: "move", thread_id: threads[0].id, folder_id: "3" }));
  expect(await screen.findByRole("status")).toHaveTextContent("已移至“客户 / 亚洲 / 新加坡”");
  expect(destination).not.toHaveAttribute("data-drop-target");
  expect(screen.getByLabelText("当前地址")).toHaveTextContent("/t/active");
});

it("ignores foreign mailbox/user payloads, external links and malformed payloads", () => {
  const c = makeController(); mount(c);
  const destination = screen.getByRole("link", { name: "客户" }).parentElement!;
  for (const otherScope of [JSON.stringify(["other@example.com", "Larry"]), JSON.stringify(["sales@example.com", "Other"])]) {
    const data = transfer(); startMailDrag(data, otherScope, "10"); fireEvent.drop(destination, { dataTransfer: data });
  }
  const external = transfer(); external.setData("text/uri-list", "https://example.com");
  fireEvent.dragOver(destination, { dataTransfer: external });
  expect(destination).not.toHaveAttribute("data-drop-target");
  fireEvent.drop(destination, { dataTransfer: external });
  external.setData(MAIL_DRAG_TYPE, "{"); fireEvent.drop(destination, { dataTransfer: external });
  expect(c.command).not.toHaveBeenCalled();
});

it("blocks duplicate in-flight drops and shows failures without claiming a move succeeded", async () => {
  const c = makeController(); let finish!: (value: string) => void;
  c.command = vi.fn(() => new Promise<string>(resolve => { finish = resolve; }));
  mount(c); const destination = screen.getByRole("link", { name: "客户" }).parentElement!;
  const data = transfer(); startMailDrag(data, scope, "10");
  fireEvent.drop(destination, { dataTransfer: data }); fireEvent.drop(destination, { dataTransfer: data });
  expect(c.command).toHaveBeenCalledTimes(1); finish("保存失败，请重试");
  expect(await screen.findByRole("alert")).toHaveTextContent("保存失败，请重试");
  expect(screen.queryByText(/已移至/)).not.toBeInTheDocument();
  fireEvent.drop(destination, { dataTransfer: data }); expect(c.command).toHaveBeenCalledTimes(2); finish("");
  expect(await screen.findByRole("status")).toHaveTextContent("已移至“客户”");
});

it("does not send a move for the current folder or while folder commands are busy", () => {
  const c = makeController(); c.data.assignments["10"] = "1"; const view = mount(c);
  const data = transfer(); startMailDrag(data, scope, "10");
  fireEvent.drop(screen.getByRole("link", { name: "客户" }).parentElement!, { dataTransfer: data });
  expect(screen.getByRole("status")).toHaveTextContent("这条会话已在“客户”");
  c.busy = true;
  view.rerender(<MemoryRouter><MailFolderTree controller={c} dragScope={scope} /></MemoryRouter>);
  fireEvent.drop(screen.getByRole("link", { name: "亚洲" }).parentElement!, { dataTransfer: data });
  expect(c.command).not.toHaveBeenCalled();
});
