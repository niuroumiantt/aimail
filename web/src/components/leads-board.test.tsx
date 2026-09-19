import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import type { LeadSuggestion, OutboxStatus } from "@/data/types";
import { LeadsBoard } from "./leads-board";
import { TipProvider } from "./tip";

const suggestion: LeadSuggestion = {
  id: "s1",
  thread_id: "t1",
  company: "Aurora",
  contact: "Mikko",
  wants: "2U 服务器",
  quantity: "480 台",
  region: "赫尔辛基",
  priority: "high",
  unverified: ["480"],
  model: "Spark · fast",
  task_version: "extract_lead@1",
  produced_at: "2026-09-19T08:00:00+08:00",
};

function show(user: string, onSetUser = vi.fn(), outbox?: OutboxStatus) {
  const noop = async () => "";
  render(
    <MemoryRouter>
      <TipProvider>
        <LeadsBoard
          suggestions={[suggestion]}
          failed={2}
          leads={[]}
          outbox={outbox}
          threadIds={new Set(["t1"])}
          user={user}
          onSetUser={onSetUser}
          onConfirm={noop}
          onDismiss={noop}
          onUpdateLead={noop}
        />
      </TipProvider>
    </MemoryRouter>,
  );
  return onSetUser;
}

it("asks for a name before anyone can confirm", () => {
  const onSetUser = show("");
  const input = screen.getByPlaceholderText("例如 Larry");
  fireEvent.change(input, { target: { value: "Larry" } });
  fireEvent.click(screen.getByRole("button", { name: "记住" }));
  expect(onSetUser).toHaveBeenCalledWith("Larry");
});

it("does not ask for a name once there is one", () => {
  show("Larry");
  expect(screen.queryByPlaceholderText("例如 Larry")).not.toBeInTheDocument();
});

it("shows unverified numbers on a suggestion before confirmation", () => {
  show("Larry");
  expect(screen.getByRole("alert")).toHaveTextContent("480");
});

it("counts inquiries whose lead extraction failed", () => {
  show("Larry");
  expect(screen.getByText(/没提出线索/)).toHaveTextContent("2");
});

it("shows undelivered pushes so nobody assumes the OA got them", () => {
  show("Larry", vi.fn(), { configured: true, pending: 0, failed: 2, delivered: 5, last_error: "HTTP 503" });
  expect(screen.getByText(/推送未送达/)).toHaveTextContent("2");
});

it("says nothing about pushes when no webhook is configured or all went through", () => {
  show("Larry", vi.fn(), { configured: false, pending: 0, failed: 3, delivered: 0, last_error: "" });
  expect(screen.queryByText(/推送未送达/)).not.toBeInTheDocument();
});

it("offers the CSV export of confirmed leads", () => {
  show("Larry");
  expect(screen.getByRole("link", { name: /导出 CSV/ })).toHaveAttribute("href", "/api/leads.csv");
});
