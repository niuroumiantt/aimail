import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Reading } from "@/data/types";
import { ReadingCard } from "./reading-card";
import { TipProvider } from "./tip";

const base = { model: "Spark · fast", task_version: "summarize_inquiry@2", produced_at: "2026-09-19T08:13:41+08:00" };
const ok: Reading = {
  ...base,
  status: "ok",
  is_inquiry: true,
  language: "en",
  summary_zh: "客户要 48 台。",
  summary_en: "Customer needs 48 units.",
  facts: ["48 台"],
  quoted_numbers: ["48"],
  unverified: [],
};

function show(reading?: Reading) {
  return render(
    <TipProvider>
      <ReadingCard reading={reading} />
    </TipProvider>,
  );
}

describe("读数卡", () => {
  it("shows who produced the reading", () => {
    show(ok);
    const sig = screen.getByTestId("attribution");
    expect(sig).toHaveTextContent("Spark · fast");
    expect(sig).toHaveTextContent("summarize_inquiry@2");
  });

  it("puts the warning above a summary with unverified numbers and dims it", () => {
    show({ ...ok, quoted_numbers: ["48", "1200"], unverified: ["1200"] });
    const card = screen.getByTestId("reading-ok");
    const alarm = within(card).getByRole("alert");
    const summary = within(card).getByTestId("summary");
    expect(alarm).toHaveTextContent("1200");
    // 警告在摘要之前(DOM 顺序 = 阅读顺序)
    expect(alarm.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(summary).toHaveAttribute("data-suspect", "true");
  });

  it("renders the failure state instead of an empty summary", () => {
    show({ ...base, status: "failed", reason: "两次都没给出合规 JSON" });
    const card = screen.getByTestId("reading-failed");
    expect(card).toHaveTextContent("这封没有读数");
    expect(card).toHaveTextContent("两次都没给出合规 JSON");
    expect(screen.queryByTestId("summary")).not.toBeInTheDocument();
  });

  it("labels a non-inquiry as such", () => {
    show({ ...ok, is_inquiry: false, summary_zh: "这是推销。" });
    expect(screen.getByRole("heading", { name: "AI 判断:这不是询盘" })).toBeInTheDocument();
  });

  it("says plainly when there is no reading yet", () => {
    show(undefined);
    expect(screen.getByTestId("reading-none")).toHaveTextContent("还没有读数");
  });
});
