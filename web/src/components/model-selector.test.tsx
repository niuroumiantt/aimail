import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ModelProvider, ModelSelection } from "@/data/types";
import { apiSource } from "@/data/source";
import { ModelSelector } from "./model-selector";

const selection = (selected: ModelProvider = "local"): ModelSelection => ({
  selected, model: `${selected}-model`, options: [
    { id: "codex_cli", label: "Codex CLI", available: true, model: "codex-test", reason: "登录及连接在运行时核验" },
    { id: "claude_code_cli", label: "Claude Code CLI", available: false, model: "", reason: "服务器未安装 CLI" },
    { id: "local", label: "Spark", available: true, model: "qwen-test", reason: "" },
  ],
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const open = () => fireEvent.click(screen.getByRole("button", { name: /选择邮件识别模型/ }));

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("shows all three disabled choices while connection state is pending without inventing a selection", async () => {
  const pending = deferred<ModelSelection>();
  const load = vi.fn().mockReturnValue(pending.promise);
  const save = vi.fn();
  render(<ModelSelector mailbox="sales@test" load={load} save={save} />);
  open();
  expect(screen.getByRole("status")).toHaveTextContent("正在读取可用模型");
  for (const label of ["Codex CLI", "Claude Code CLI", "Spark"]) {
    const option = screen.getByRole("button", { name: new RegExp(`^${label}`) });
    expect(option).toBeDisabled();
    expect(option).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(option);
  }
  expect(save).not.toHaveBeenCalled();
  expect(load).toHaveBeenCalledTimes(1);
  await act(async () => pending.resolve(selection()));
  expect(screen.getByRole("button", { name: /^Spark/ })).toHaveAttribute("aria-pressed", "true");
});

it("keeps a choice missing from the catalogue disabled and unselected", async () => {
  const state = selection();
  const save = vi.fn();
  render(<ModelSelector mailbox="sales@test" load={vi.fn().mockResolvedValue({ ...state, options: state.options.filter(option => option.id !== "local") })} save={save} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：local-model · 服务默认" });
  open();
  const option = screen.getByRole("button", { name: /^Spark/ });
  expect(option).toBeDisabled();
  expect(option).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(option);
  expect(save).not.toHaveBeenCalled();
});

it("surfaces a stalled catalogue timeout and retries only its GET before enabling verified choices", async () => {
  vi.useFakeTimers();
  const stalled = deferred<Response>();
  const fetcher = vi.fn().mockReturnValueOnce(stalled.promise).mockResolvedValueOnce(Response.json(selection()));
  vi.stubGlobal("fetch", fetcher);
  const source = apiSource("sales@test");
  const save = vi.fn();
  render(<ModelSelector mailbox="sales@test" load={source.modelSelection} save={save} />);
  open();
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(screen.getByRole("alert")).toHaveTextContent("读取超时，请检查连接后重试。");
  for (const label of ["Codex CLI", "Claude Code CLI", "Spark"]) {
    expect(screen.getByRole("button", { name: new RegExp(`^${label}`) })).toBeDisabled();
  }
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重新读取" })); });
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Spark" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Codex CLI/ })).toBeEnabled();
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls.every(([path, init]) => path === "/api/model-selection" && !init.method)).toBe(true);
  expect(save).not.toHaveBeenCalled();
  await act(async () => stalled.resolve(Response.json(selection("codex_cli"))));
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Spark" })).toBeInTheDocument();
});

it("lists all three providers, explains unavailable options, and saves without model work", async () => {
  const load = vi.fn().mockResolvedValue(selection());
  const save = vi.fn().mockResolvedValue(selection("codex_cli"));
  render(<ModelSelector mailbox="sales@test" load={load} save={save} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Spark" });
  open();
  expect(screen.getByRole("button", { name: /Claude Code CLI/ })).toBeDisabled();
  expect(screen.getByText("未连接 · 服务器未安装 CLI")).toBeInTheDocument();
  expect(screen.getByText("用于新分析；已有摘要保留")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /^Codex CLI/ }));
  await screen.findByRole("button", { name: "选择邮件识别模型：Codex CLI" });
  expect(save).toHaveBeenCalledExactlyOnceWith("codex_cli");
  expect(load).toHaveBeenCalledTimes(1);
});

it.each([new Error("CLI 登录失效，选择未保存"), selection()])("keeps the original selection when saving fails or returns another provider", async response => {
  const save = response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response);
  render(<ModelSelector mailbox="sales@test" load={vi.fn().mockResolvedValue(selection())} save={save} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Spark" });
  open();
  fireEvent.click(screen.getByRole("button", { name: /^Codex CLI/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(response instanceof Error ? response.message : "服务端没有保存所选模型");
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Spark" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Spark/ })).toHaveAttribute("aria-pressed", "true");
});

it("ignores a previous mailbox's late load and save, and keeps the next mailbox usable", async () => {
  const oldLoad = deferred<ModelSelection>();
  const oldSave = deferred<ModelSelection>();
  const load = vi.fn().mockReturnValueOnce(oldLoad.promise).mockResolvedValue(selection("codex_cli"));
  const view = render(<ModelSelector mailbox="old@test" load={load} save={vi.fn()} />);
  view.rerender(<ModelSelector mailbox="new@test" load={load} save={vi.fn()} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Codex CLI" });
  await act(async () => oldLoad.resolve(selection()));
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Codex CLI" })).toBeInTheDocument();
  const saving = vi.fn().mockReturnValue(oldSave.promise);
  const currentLoad = vi.fn().mockResolvedValue(selection());
  view.rerender(<ModelSelector mailbox="sales@test" load={currentLoad} save={saving} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Spark" });
  open();
  fireEvent.click(screen.getByRole("button", { name: /^Codex CLI/ }));
  await waitFor(() => expect(saving).toHaveBeenCalled());
  view.rerender(<ModelSelector mailbox="larry@test" load={load} save={vi.fn()} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Codex CLI" });
  await act(async () => oldSave.resolve(selection()));
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Codex CLI" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Spark/ })).toBeEnabled();
});

it("allows retrying a failed settings load without inventing a selected model", async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error("邮箱设置读取失败")).mockResolvedValue(selection());
  render(<ModelSelector mailbox="sales@test" load={load} save={vi.fn()} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：尚未加载" });
  open();
  expect(await screen.findByRole("alert")).toHaveTextContent("邮箱设置读取失败");
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByRole("button", { name: "选择邮件识别模型：Spark" });
  expect(load).toHaveBeenCalledTimes(2);
});

it("labels a legacy provider as the service default without calling it a CLI", async () => {
  render(<ModelSelector mailbox="sales@test" load={vi.fn().mockResolvedValue({ ...selection(), selected: "claude", model: "legacy-anthropic" })} save={vi.fn()} />);
  expect(await screen.findByRole("button", { name: "选择邮件识别模型：legacy-anthropic · 服务默认" })).toBeInTheDocument();
  open();
  expect(screen.getByText(/当前服务默认：legacy-anthropic/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Claude Code CLI/ })).toHaveAttribute("aria-pressed", "false");
});

it("refreshes metadata only and cannot let a late connection refresh undo a successful save", async () => {
  const fresh = deferred<ModelSelection>();
  const load = vi.fn().mockResolvedValueOnce(selection()).mockReturnValueOnce(fresh.promise);
  const save = vi.fn().mockResolvedValue(selection("codex_cli"));
  render(<ModelSelector mailbox="sales@test" load={load} save={save} />);
  await screen.findByRole("button", { name: "选择邮件识别模型：Spark" });
  open();
  fireEvent.click(screen.getByRole("button", { name: "刷新模型连接状态" }));
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /^Codex CLI/ }));
  await screen.findByRole("button", { name: "选择邮件识别模型：Codex CLI" });
  await act(async () => fresh.resolve(selection()));
  expect(screen.getByRole("button", { name: "选择邮件识别模型：Codex CLI" })).toBeInTheDocument();
  expect(save).toHaveBeenCalledExactlyOnceWith("codex_cli");
});
