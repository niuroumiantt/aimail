import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { threads } from "@/fixtures/threads";
import { dateGroup, ThreadList } from "./thread-list";
import { TipProvider } from "./tip";

afterEach(() => { localStorage.clear(); vi.useRealTimers(); });

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
