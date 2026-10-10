import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import type { FolderController } from "@/data/mail-folders";
import { MailFolderTree, MoveToFolder } from "./mail-folder-tree";

function controller(): FolderController {
  return { data: { items: [{ id: "1", parent_id: null, name: "客户", count: 0 }, { id: "2", parent_id: "1", name: "亚洲", count: 0 }, { id: "3", parent_id: "2", name: "新加坡超长的客户文件夹名称", count: 1 }], assignments: { "10": "3" } }, error: "", busy: false, enabled: true, command: vi.fn(async () => "") };
}
it("renders three compact nested levels, selection and the full path", () => {
  render(<MemoryRouter initialEntries={["/?cf=3"]}><MailFolderTree controller={controller()} /></MemoryRouter>);
  const leaf = screen.getByRole("link", { name: /新加坡超长/ });
  expect(leaf).toHaveAttribute("aria-current", "page");
  expect(leaf).toHaveAttribute("title", "客户 / 亚洲 / 新加坡超长的客户文件夹名称");
  expect(leaf.closest("div")).toHaveStyle({ paddingLeft: "24px" });
});
it("creates a named root folder only on explicit save", async () => {
  const c = controller();
  render(<MemoryRouter><MailFolderTree controller={c} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "新建文件夹" }));
  fireEvent.change(screen.getByLabelText("文件夹名称"), { target: { value: "待办" } });
  expect(c.command).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(c.command).toHaveBeenCalledWith({ action: "create", name: "待办", parent_id: null }));
});
it("moves the whole conversation using full paths and can remove folder membership", async () => {
  const c = controller();
  render(<MemoryRouter><MoveToFolder controller={c} threadId="10" /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "移动" }));
  expect(screen.getByLabelText("目标文件夹")).toHaveValue("3");
  fireEvent.change(screen.getByLabelText("目标文件夹"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "确定" }));
  await waitFor(() => expect(c.command).toHaveBeenCalledWith({ action: "move", thread_id: "10", folder_id: null }));
});
