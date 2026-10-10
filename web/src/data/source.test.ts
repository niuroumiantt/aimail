import { afterEach, expect, it, vi } from "vitest";
import { apiSource, type DataSource } from "./source";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("bounds a stalled GET, aborts it, and retries only when requested", async () => {
  vi.useFakeTimers();
  const stalled = deferred<Response>();
  const fetcher = vi.fn().mockReturnValueOnce(stalled.promise)
    .mockResolvedValueOnce(Response.json({ selected: "local", model: "Spark · fast", options: [] }));
  vi.stubGlobal("fetch", fetcher);
  const source = apiSource("sales@example.test");
  const request = source.modelSelection();
  const failure = expect(request).rejects.toThrow("读取超时，请检查连接后重试。");
  const init = fetcher.mock.calls[0][1] as RequestInit;
  const signal = init.signal!;
  expect(new Headers(init.headers).get("X-Mailbox-Address")).toBe("sales@example.test");
  await vi.advanceTimersByTimeAsync(19_999);
  expect(signal.aborted).toBe(false);
  expect(fetcher).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  await failure;
  expect(signal.aborted).toBe(true);
  await vi.advanceTimersByTimeAsync(60_000);
  expect(fetcher).toHaveBeenCalledTimes(1);
  await expect(source.modelSelection()).resolves.toMatchObject({ selected: "local" });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls.every(([, options]) => !options.method)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  stalled.resolve(Response.json({ selected: "codex_cli" }));
});

it("turns a fetch AbortError into the safe read timeout", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn((_path: string, init: RequestInit) => new Promise<Response>((_, reject) => {
    init.signal!.addEventListener("abort", () => reject(new DOMException("Private transport error", "AbortError")));
  })));
  const failure = expect(apiSource().mailbox()).rejects.toThrow("读取超时，请检查连接后重试。");
  await vi.advanceTimersByTimeAsync(20_000);
  await failure;
});

it.each([200, 503])("keeps the GET deadline through a stalled JSON body after HTTP %s headers", async status => {
  vi.useFakeTimers();
  const headers = deferred<Response>();
  const body = deferred<unknown>();
  const response = new Response(null, { status, statusText: status === 503 ? "Service Unavailable" : "OK" });
  const json = vi.spyOn(response, "json").mockReturnValue(body.promise);
  const fetcher = vi.fn().mockReturnValue(headers.promise);
  vi.stubGlobal("fetch", fetcher);
  const failure = expect(apiSource().threads()).rejects.toThrow("读取超时，请检查连接后重试。");
  await vi.advanceTimersByTimeAsync(19_000);
  headers.resolve(response);
  await vi.advanceTimersByTimeAsync(0);
  expect(json).toHaveBeenCalledTimes(1);
  const signal = (fetcher.mock.calls[0][1] as RequestInit).signal!;
  await vi.advanceTimersByTimeAsync(999);
  expect(signal.aborted).toBe(false);
  await vi.advanceTimersByTimeAsync(1);
  await failure;
  expect(signal.aborted).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  body.resolve(status === 200 ? [] : { detail: "Late server error" });
});

it("clears read deadlines after normal success or an HTTP error", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json([]))
    .mockResolvedValueOnce(Response.json({ detail: "不能访问这个邮箱" }, { status: 403 }));
  vi.stubGlobal("fetch", fetcher);
  await expect(apiSource().threads()).resolves.toEqual([]);
  await expect(apiSource().mailbox()).rejects.toThrow("不能访问这个邮箱");
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(20_000);
  expect(fetcher.mock.calls.every(([, init]) => !init.signal.aborted)).toBe(true);
});

const writes: [string, (source: DataSource) => Promise<unknown>][] = [
  ["POST", source => source.analyzeThread("1")],
  ["POST translation", source => source.translateMessage("1")],
  ["PATCH", source => source.updateLead("1", { next_step: "Follow up" }, "Operator")],
  ["PUT", source => source.setModelSelection("codex_cli", "Operator")],
];

it.each(writes)("leaves %s pending without a read deadline, cancellation or automatic retry", async (method, start) => {
  vi.useFakeTimers();
  const response = deferred<Response>();
  const fetcher = vi.fn().mockReturnValue(response.promise);
  vi.stubGlobal("fetch", fetcher);
  const request = start(apiSource());
  let settled = false;
  void request.then(() => { settled = true; });
  await vi.advanceTimersByTimeAsync(60_000);
  expect(settled).toBe(false);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][1].method).toBe(method.split(" ")[0]);
  expect(fetcher.mock.calls[0][1].signal).toBeUndefined();
  expect(vi.getTimerCount()).toBe(0);
  response.resolve(Response.json({}));
  await request;
});

it("scopes cached translation reads and explicit requests to their original mailbox", async () => {
  const response = deferred<Response>();
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(null))
    .mockReturnValueOnce(response.promise).mockResolvedValueOnce(Response.json(null));
  vi.stubGlobal("fetch", fetcher);
  const sales = apiSource("sales@example.test");
  expect(await sales.getMessageTranslation("3")).toBeNull();
  const translating = sales.translateMessage("3");
  const privateMailbox = sales.selectMailbox("private@example.test");
  await privateMailbox.getMessageTranslation("4");
  response.resolve(Response.json({ status: "ok", text_zh: "已翻译", model: "Original model" }));
  await expect(translating).resolves.toMatchObject({ model: "Original model" });
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
    "/api/messages/3/translation", "/api/messages/3/translation", "/api/messages/4/translation",
  ]);
  expect(fetcher.mock.calls.map(([, init]) => new Headers(init.headers).get("X-Mailbox-Address")))
    .toEqual(["sales@example.test", "sales@example.test", "private@example.test"]);
  expect(fetcher.mock.calls[1][1].method).toBe("POST");
});

it("does not cancel or repeat an uncertain send after the token was issued", async () => {
  vi.useFakeTimers();
  const sendResponse = deferred<Response>();
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ token: "once-only" }))
    .mockReturnValueOnce(sendResponse.promise);
  vi.stubGlobal("fetch", fetcher);
  const request = apiSource("sales@example.test").send("1", { to: ["customer@example.test"], subject: "Reply", body: "Thanks." }, "Operator");
  await vi.advanceTimersByTimeAsync(60_000);
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual(["/api/threads/1/send-token", "/api/threads/1/send"]);
  expect(fetcher.mock.calls.every(([, init]) => init.method === "POST" && init.signal === undefined)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  sendResponse.resolve(Response.json({}));
  await request;
});

it("loads original attachment bytes in the mailbox where the click started", async () => {
  const blob = new Blob(["%PDF-1.7 original bytes"], { type: "application/pdf" });
  const response = { ok: true, blob: vi.fn(async () => blob) };
  const fetcher = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetcher);
  const sales = apiSource("sales@example.test");
  const request = sales.attachmentFile("42");
  sales.selectMailbox("other@example.test");
  await expect(request).resolves.toBe(blob);
  expect(fetcher.mock.calls[0][0]).toBe("/api/attachments/42/file");
  expect(new Headers((fetcher.mock.calls[0][1] as RequestInit).headers).get("X-Mailbox-Address")).toBe("sales@example.test");
});

it("keeps folder requests and forwarding in the mailbox where the action began", async () => {
  const fetcher = vi.fn().mockImplementation(async (url: string) => url.endsWith("send-token") ? Response.json({ token: "one-use" }) : Response.json({ items: [], assignments: {} }));
  vi.stubGlobal("fetch", fetcher);
  const source = apiSource("sales@example.test");
  await source.mailFolders("Larry", { action: "create", name: "客户", parent_id: null });
  await source.mailFolders("Larry", { action: "move", thread_id: "10", folder_id: "3" });
  await source.send("10", { to: ["buyer@example.test"], subject: "Fwd: RFQ", body: "", forward_message_id: "11", include_attachments: true }, "Larry");
  for (const [, init] of fetcher.mock.calls) expect(new Headers(init.headers).get("X-Mailbox-Address")).toBe("sales@example.test");
  expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).toMatchObject({ token: "one-use", forward_message_id: "11", include_attachments: true });
});
