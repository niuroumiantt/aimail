import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { OutreachWorkspace } from "./outreach-workspace";

afterEach(() => vi.unstubAllGlobals());

it("hands off a prospect without requesting an approval or sending mail", async () => {
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    requests.push(path);
    if (path.endsWith("/assignment")) {
      expect(JSON.parse(options?.body as string)).toEqual({action:"offer",recipient:"cloud@example.test",version:0});
    }
    return new Response(JSON.stringify({enabled:false, sender:"larry@example.test", identity:"larry@example.test",
      assignment_members:["larry@example.test","cloud@example.test"], items:[{id:"p1",email:"customer@example.test",state:"draft",payload:{company:"Prospect",country:"US",tier:"1D"},steps:[]}]}));
  }));
  render(<MemoryRouter><OutreachWorkspace /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", {name:/Prospect/}));
  fireEvent.change(screen.getByLabelText("潜客接收人"), {target:{value:"cloud@example.test"}});
  fireEvent.click(screen.getByRole("button", {name:"提交潜客交接"}));
  await waitFor(() => expect(requests).toContain("/api/prospects/p1/assignment"));
  expect(requests.every(path => path === "/api/prospects" || path.endsWith("/assignment"))).toBe(true);
});

it("requires six complete messages and explicit confirmation before approving outreach", async () => {
  const requests: { path: string; body?: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    requests.push({path, body: options?.body as string | undefined});
    const data = path.endsWith("approval-token") ? {token: "one-use"} : path.endsWith("approve") ? {ok:true} : {
      enabled: false, items: [{id: "p1", email: "support@fictional.example", state: "draft",
        payload: {company: "Fictional Colo", country: "US", tier: "1D"}, steps: []}],
    };
    return new Response(JSON.stringify(data), {status:200});
  }));
  render(<MemoryRouter><OutreachWorkspace /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", {name: /Fictional Colo/}));
  const approve = screen.getByRole("button", {name:"批准这家公司的六封序列"});
  expect(approve).toBeDisabled();
  for (const day of [0,7,14,28,60,90]) {
    fireEvent.change(screen.getByLabelText(`第 ${day} 天标题`), {target:{value:"Approved test subject"}});
    fireEvent.change(screen.getByLabelText(`第 ${day} 天正文`), {target:{value:"Approved test body"}});
  }
  expect(approve).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(approve).toBeEnabled();
  fireEvent.click(approve);
  await waitFor(() => expect(requests.some(r => r.path.endsWith("/approve"))).toBe(true));
  const request = requests.find(r => r.path.endsWith("/approve"));
  const payload = JSON.parse(request?.body ?? "{}");
  expect(payload.steps.map((s: {day:number}) => s.day)).toEqual([0,7,14,28,60,90]);
  expect(payload.token).toBe("one-use");
  expect(payload.policy_confirmed).toBe(true);
});

it("lets the accepted owner approve with their personal sender after handoff", async () => {
  let accepted = false;
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    requests.push(path);
    if (path.endsWith("/assignment")) {
      expect(JSON.parse(options?.body as string)).toEqual({action:"accept",recipient:"",version:1});
      accepted = true;
      return new Response(JSON.stringify({owner:"cloud@example.test",pending:"",version:2}));
    }
    if (path.endsWith("/approval-token")) return new Response(JSON.stringify({token:"one-use"}));
    if (path.endsWith("/approve")) return new Response(JSON.stringify({ok:true}));
    return new Response(JSON.stringify({enabled:false, sender:"cloud@example.test",
      identity:"cloud@example.test", default_owner:"larry@example.test",
      assignment_members:["larry@example.test","cloud@example.test"],
      items:[{id:"p1",email:"customer@example.test",state:"draft",
        payload:{company:"Fictional Handoff",country:"US",tier:"1D"},steps:[],
        assignment:{owner:accepted ? "cloud@example.test" : "larry@example.test",
          pending:accepted ? "" : "cloud@example.test",version:accepted ? 2 : 1}}]}));
  }));
  render(<MemoryRouter><OutreachWorkspace /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", {name:/Fictional Handoff/}));
  expect(screen.getByText(/请先完成潜客交接/)).toBeTruthy();
  expect(screen.getByRole("button", {name:"批准这家公司的六封序列"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button", {name:"确认接手潜客"}));
  await waitFor(() => expect(requests.filter(path => path.endsWith("/assignment"))).toHaveLength(1));
  await waitFor(() => expect(screen.queryByText(/请先完成潜客交接/)).toBeNull());
  const approve = screen.getByRole("button", {name:"批准这家公司的六封序列"});
  for (const day of [0,7,14,28,60,90]) {
    fireEvent.change(screen.getByLabelText(`第 ${day} 天标题`), {target:{value:"Approved test subject"}});
    fireEvent.change(screen.getByLabelText(`第 ${day} 天正文`), {target:{value:"Approved test body"}});
  }
  fireEvent.click(screen.getByRole("checkbox"));
  expect(approve).toBeEnabled();
  fireEvent.click(approve);
  await waitFor(() => expect(requests.some(path => path.endsWith("/approve"))).toBe(true));
  expect(requests.some(path => path.endsWith("/approval-token"))).toBe(true);
  expect(requests.some(path => path.endsWith("/send"))).toBe(false);
});
