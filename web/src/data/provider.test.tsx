import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DataProvider, useData } from "./provider";
import { apiSource } from "./source";
import { threads as fixtures } from "@/fixtures/threads";

vi.mock("./source", async importOriginal => {
  const original = await importOriginal<typeof import("./source")>();
  return { ...original, chooseSource: async () => original.apiSource() };
});
const SALES = "sales@example.test";
const LARRY = "larry@example.test";
const info = (address: string) => ({ address, display_name: address, tasks: ["read", "leads", "draft"] });
const thread = (address: string) => ({ ...fixtures[0], id: "1", subject: address });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function Probe() {
  const data = useData();
  return <>
    <output aria-label="mailbox">{data.mailbox.address}</output>
    <output aria-label="loading">{String(data.loading)}</output>
    <output aria-label="threads">{data.threads.map(t => t.subject).join(",")}</output>
    <output aria-label="details">{Object.values(data.details).map(t => t.subject).join(",")}</output>
    <output aria-label="error">{data.error}</output>
    <button onClick={() => void data.selectMailbox(SALES)}>Sales</button>
    <button onClick={() => void data.selectMailbox(LARRY)}>Larry</button>
    <button onClick={() => void data.openThread("1")}>Read</button>
  </>;
}
function serve(override: (path: string, address: string) => Promise<Response> | undefined = () => undefined) {
  const fetcher = vi.fn((path: string, init?: RequestInit) => {
    const address = new Headers(init?.headers).get("X-Mailbox-Address") ?? SALES;
    const custom = override(path, address);
    if (custom) return custom;
    const values: Record<string, unknown> = {
      "/api/mailboxes": { default: SALES, items: [info(SALES), info(LARRY)] },
      "/api/mailbox": info(address), "/api/threads": [thread(address)],
      "/api/leads/suggestions": [], "/api/leads/failed": { count: 0 }, "/api/leads": [],
      "/api/outbox": { configured: false, pending: 0, failed: 0, delivered: 0, last_error: "" },
      "/api/threads/1": thread(address),
    };
    return Promise.resolve(Response.json(values[path] ?? {}));
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

it("shows mail before slow secondary lead data completes", async () => {
  const slow = deferred<Response>();
  serve(path => path === "/api/leads" ? slow.promise : undefined);
  render(<DataProvider><Probe /></DataProvider>);
  await waitFor(() => expect(screen.getByLabelText("threads")).toHaveTextContent(SALES));
  expect(screen.getByLabelText("loading")).toHaveTextContent("false");
  await act(async () => slow.resolve(Response.json([])));
});

it("switches the label immediately and ignores both late lists and late details", async () => {
  const slowList = deferred<Response>();
  const slowDetail = deferred<Response>();
  const fetcher = serve((path, address) => {
    if (path === "/api/threads" && address === LARRY) return slowList.promise;
    if (path === "/api/threads/1") return slowDetail.promise;
  });
  render(<DataProvider><Probe /></DataProvider>);
  await waitFor(() => expect(screen.getByLabelText("threads")).toHaveTextContent(SALES));
  fireEvent.click(screen.getByText("Read"));
  fireEvent.click(screen.getByText("Read"));
  expect(fetcher.mock.calls.filter(([path]) => path === "/api/threads/1")).toHaveLength(1);
  fireEvent.click(screen.getByText("Larry"));
  expect(screen.getByLabelText("mailbox")).toHaveTextContent(LARRY);
  expect(screen.getByLabelText("threads")).toBeEmptyDOMElement();
  expect(screen.getByLabelText("details")).toBeEmptyDOMElement();
  expect(screen.getByLabelText("loading")).toHaveTextContent("true");
  fireEvent.click(screen.getByText("Sales"));
  await waitFor(() => expect(screen.getByLabelText("threads")).toHaveTextContent(SALES));
  await act(async () => {
    slowList.resolve(Response.json([thread(LARRY)]));
    slowDetail.resolve(Response.json(thread("stale detail")));
  });
  expect(screen.getByLabelText("mailbox")).toHaveTextContent(SALES);
  expect(screen.getByLabelText("threads")).toHaveTextContent(SALES);
  expect(screen.getByLabelText("details")).toBeEmptyDOMElement();
});

it("clears old mail and surfaces a denied mailbox instead of retaining private data", async () => {
  serve((path, address) => path === "/api/threads" && address === LARRY
    ? Promise.resolve(Response.json({ detail: "不能访问这个邮箱" }, { status: 403 })) : undefined);
  render(<DataProvider><Probe /></DataProvider>);
  await waitFor(() => expect(screen.getByLabelText("threads")).toHaveTextContent(SALES));
  fireEvent.click(screen.getByText("Larry"));
  await waitFor(() => expect(screen.getByLabelText("error")).toHaveTextContent("不能访问这个邮箱"));
  expect(screen.getByLabelText("threads")).toBeEmptyDOMElement();
  expect(screen.getByLabelText("loading")).toHaveTextContent("false");
});

it("keeps token issuance and sending in the original mailbox across a switch", async () => {
  const token = deferred<Response>();
  const fetcher = serve(path => path.endsWith("/send-token") ? token.promise : undefined);
  const sales = apiSource(SALES);
  const send = sales.send("1", { to: ["customer@example.test"], subject: "RFQ", body: "Test only" }, "Tester");
  const larry = sales.selectMailbox(LARRY);
  token.resolve(Response.json({ token: "test-token" }));
  await send;
  await larry.threads();
  expect(fetcher.mock.calls.map(([, init]) => new Headers(init?.headers).get("X-Mailbox-Address")))
    .toEqual([SALES, SALES, LARRY]);
});
