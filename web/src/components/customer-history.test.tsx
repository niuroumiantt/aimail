import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import type { HistoryItem, Thread } from "@/data/types";
import { CustomerHistory } from "./customer-history";
import { ThreadDetail } from "./thread-detail";
import { TipProvider } from "./tip";

const past: HistoryItem = {
  id: "t-old",
  subject: "RFQ 20 x R740 servers",
  first_at: "2026-06-02T09:00:00+08:00",
  last_at: "2026-06-09T09:00:00+08:00",
  folder: "replied",
  replied: true,
  lead_status: "won",
  excerpt: "We need 20 × Dell R740 servers.",
};

const thread: Thread = {
  id: "t-new",
  subject: "Re: our order",
  company: "Aurora",
  contact: "Mikko Laine",
  email: "mikko@aurora.test",
  region: "",
  scale: "1 封",
  folder: "inbox",
  updated_at: "2026-09-01T09:00:00+08:00",
  messages: [],
};

const wrap = (node: React.ReactNode) =>
  render(
    <MemoryRouter>
      <TipProvider>{node}</TipProvider>
    </MemoryRouter>,
  );

it("shows past dealings with their outcome and a way back to them", () => {
  wrap(<CustomerHistory items={[past]} />);
  expect(screen.getByTestId("customer-history")).toHaveTextContent("此前 1 次往来");
  expect(screen.getByTestId("customer-history")).toHaveTextContent("成交 1");
  expect(screen.getByRole("link", { name: "RFQ 20 x R740 servers" })).toHaveAttribute("href", "/t/t-old");
});

it("marks a first-time customer in the thread header", () => {
  wrap(<ThreadDetail thread={{ ...thread, history: [] }} backSearch="" />);
  expect(screen.getByText("第一次来信")).toBeInTheDocument();
  expect(screen.queryByTestId("customer-history")).not.toBeInTheDocument();
});

it("says nothing about history until the detail has loaded", () => {
  wrap(<ThreadDetail thread={thread} backSearch="" />);
  expect(screen.queryByText("第一次来信")).not.toBeInTheDocument();
});

it("shows the history card for a returning customer", () => {
  wrap(<ThreadDetail thread={{ ...thread, history: [past] }} backSearch="" />);
  expect(screen.getByTestId("customer-history")).toHaveTextContent("R740");
  expect(screen.queryByText("第一次来信")).not.toBeInTheDocument();
});
