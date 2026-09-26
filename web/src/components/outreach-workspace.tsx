import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/button";
import { getUser, setUser } from "@/lib/user";

const days = [0, 7, 14, 28, 60, 90];
type Step = { day: number; subject: string; body: string; state?: string; sent_at?: string };
type Prospect = { id: string; email: string; state: string; first_sent_at: string | null;
  approved_by: string | null; payload: { company: string; country: string; tier: string };
  assignment?: {owner:string;pending:string;version:number}|null; steps: Step[] };
const names: Record<string, string> = { draft: "待确认六封内容", active: "序列已批准",
  completed: "六封已完成", paused: "已暂停", replied: "收到回复 · 已停止", bounced: "退信 · 已停止",
  unsubscribed: "已退订", delivery_unknown: "发送结果待核对", pending: "等待计划时间",
  smtp_accepted: "SMTP 已接受", skipped_late: "过期节点已跳过", sending: "正在发送" };

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-User": getUser(), "X-Outreach-Action": "confirm-v1" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "服务响应异常" }));
    throw new Error(typeof error.detail === "string" ? error.detail : `请求失败 (${response.status})`);
  }
  return response.json();
}

export function OutreachWorkspace() {
  const [items, setItems] = useState<Prospect[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [sender, setSender] = useState("");
  const [defaultOwner, setDefaultOwner] = useState("");
  const [identity, setIdentity] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [recipient, setRecipient] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string>();
  const [steps, setSteps] = useState<Step[]>(days.map(day => ({ day, subject: "", body: "" })));
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [user, updateUser] = useState(getUser());
  const current = items.find(p => p.id === selected);
  const refresh = useCallback(async () => {
    try {
      const data = await api<{ items: Prospect[]; enabled: boolean; sender: string; default_owner?:string; identity?:string; assignment_members?:string[] }>("/api/prospects");
      setItems(data.items); setEnabled(data.enabled); setSender(data.sender); setError("");
      setIdentity(data.identity ?? ""); setMembers(data.assignment_members ?? []);
      setDefaultOwner(data.default_owner ?? data.sender);
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { const first = setTimeout(() => void refresh(), 0);
    const timer = setInterval(() => void refresh(), 10000);
    return () => { clearTimeout(first); clearInterval(timer); }; }, [refresh]);
  const choose = (p: Prospect) => {
    setSelected(p.id); setConfirmed(false);
    setRecipient("");
    setSteps(p.steps.length ? p.steps : days.map(day => ({ day, subject: "", body: "" })));
  };
  const approve = async () => {
    if (!current || !confirmed) return;
    setBusy(true);
    try {
      const { token } = await api<{ token: string }>(`/api/prospects/${current.id}/approval-token`, {});
      await api(`/api/prospects/${current.id}/approve`, { token, steps, policy_confirmed: true });
      setConfirmed(false); await refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const stop = async (reason: string) => {
    if (!current) return;
    setBusy(true);
    try { await api(`/api/prospects/${current.id}/stop`, { reason }); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const assign = async (action: string) => {
    if (!current) return;
    setBusy(true); setConfirmed(false);
    try { await api(`/api/prospects/${current.id}/assignment`, {action,recipient,version:current.assignment?.version ?? 0}); setRecipient(""); await refresh(); }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const owner = current?.assignment?.owner ?? defaultOwner;
  const mayApprove = !identity || (identity === owner && identity === sender);
  return <main className="min-h-screen bg-canvas p-6 text-ink">
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
      <div><Link className="text-brand-text" to={import.meta.env.VITE_DATA_SOURCE === "api" ? "/" : "/mail"}>← 邮箱</Link>
        <h1 className="mt-3 text-2xl font-semibold">开发信序列</h1>
        <p className="mt-2 text-sm text-ink-2">首封 + 第 7、14、28、60、90 天 · 每家公司一个公开联系入口</p></div>
      <div className="flex items-center gap-3"><label className="text-sm">本地审核人
        <input className="ml-2 rounded-md border border-line bg-surface p-2" value={user}
          placeholder="OA 登录身份由服务器提供" onChange={e => { updateUser(e.target.value); setUser(e.target.value); }} /></label>
        <Button onClick={() => void refresh()}>刷新</Button></div>
    </header>
    <p className="mb-4 rounded-lg bg-brand-wash p-4 text-sm text-brand-text">
      {enabled ? "发送开关已启用；只有批准的固定内容可按期执行。" : "实际发送开关关闭。可导入和审核，不会发出邮件。"}
      发件地址：{sender || "尚未配置"}。导入不等于发送；邮件回复、退订、退信或不确定结果都会停止序列。
    </p>
    {error && <p role="alert" className="mb-4 rounded-lg bg-surface p-4 text-danger">{error}</p>}
    <div className="grid gap-6 lg:grid-cols-3">
      <aside className="space-y-3">
        {!items.length && <p className="p-4 text-ink-2">暂无导入客户。</p>}
        {items.map(p => <button key={p.id} onClick={() => choose(p)}
          className={`w-full rounded-lg border p-4 text-left ${selected === p.id ? "border-brand bg-brand-wash" : "border-line bg-surface"}`}>
          <strong className="block">{p.payload.company}</strong>
          <span className="mt-2 block text-sm text-ink-2">{p.email}</span>
          <span className="mt-2 block text-xs text-ink-2">{p.payload.country} · Tier {p.payload.tier} · {names[p.state] ?? p.state}</span>
        </button>)}
      </aside>
      <section className="rounded-lg border border-line bg-surface p-6 lg:col-span-2">
        {!current ? <p className="text-ink-2">选择一家公司，核对收件人和六封完整内容。</p> : <>
          <h2 className="text-xl font-semibold">{current.payload.company}</h2>
          <p className="my-3 text-sm text-ink-2">固定收件人：{current.email} · {names[current.state] ?? current.state}</p>
          {members.length > 0 && <section className="my-4 space-y-3 rounded-lg border border-line p-4"><h3>首次联系前分配</h3><p>当前负责人：{owner}；待接手：{current.assignment?.pending || '无'}</p><p>分配不会批准或发送邮件。</p>{current.state === 'draft' && <>
            {identity === owner && !current.assignment?.pending && <><select aria-label="潜客接收人" value={recipient} onChange={e => setRecipient(e.target.value)}><option value="">选择销售</option>{members.filter(m => m !== identity).map(m => <option key={m}>{m}</option>)}</select><Button disabled={busy || !recipient} onClick={() => void assign('offer')}>提交潜客交接</Button></>}
            {current.assignment?.pending === identity && <Button disabled={busy} onClick={() => void assign('accept')}>确认接手潜客</Button>}
            {identity === owner && current.assignment?.pending && <Button disabled={busy} onClick={() => void assign('cancel')}>取消潜客交接</Button>}
          </>}{!mayApprove && <p>当前账号不是此序列的负责人及其个人发件账号，不能批准发送。请先完成潜客交接，或让管理员检查当前员工的个人发件配置。</p>}</section>}
          <p className="mb-5 text-sm text-ink-2">日期均从首封 SMTP 接受时计算；SMTP 接受不保证最终送达。服务停机错过的节点会跳过，不补发一串邮件。</p>
          <div className="space-y-5">{steps.map((step, index) => <fieldset key={step.day} className="rounded-lg border border-line p-4">
            <legend className="px-2 font-medium">{step.day === 0 ? "首封 · Day 0" : `第 ${step.day} 天`}</legend>
            <label className="block text-sm">标题<input aria-label={`第 ${step.day} 天标题`} className="mt-2 w-full rounded-md border border-line bg-surface p-2"
              maxLength={200} value={step.subject} disabled={current.state !== "draft" || busy}
              onChange={e => { setConfirmed(false); setSteps(old => old.map((s, i) => i === index ? { ...s, subject: e.target.value } : s)); }} /></label>
            <label className="mt-3 block text-sm">完整正文<textarea aria-label={`第 ${step.day} 天正文`} className="mt-2 w-full rounded-md border border-line bg-surface p-2"
              rows={5} maxLength={12000} value={step.body} disabled={current.state !== "draft" || busy}
              onChange={e => { setConfirmed(false); setSteps(old => old.map((s, i) => i === index ? { ...s, body: e.target.value } : s)); }} /></label>
            {step.state && <p className="mt-2 text-xs text-ink-2">{names[step.state] ?? step.state}{step.sent_at ? ` · ${new Date(step.sent_at).toLocaleString()}` : ""}</p>}
          </fieldset>)}</div>
          {current.state === "draft" ? <div className="mt-6 space-y-4">
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
              我已核对收件人和全部六封内容，确认适用地区发送政策、发件人身份、实体地址与停止联系说明；批准按上述日期发送。</label>
            <Button variant="solid" disabled={!mayApprove || !confirmed || busy || steps.some(s => !s.subject.trim() || !s.body.trim())} onClick={() => void approve()}>
              {busy ? "正在保存…" : "批准这家公司的六封序列"}</Button>
          </div> : <div className="mt-6 flex gap-3">
            <Button disabled={busy || current.state !== "active"} onClick={() => void stop("paused")}>暂停后续邮件</Button>
            <Button variant="danger" disabled={busy || current.state === "unsubscribed"} onClick={() => void stop("unsubscribed")}>登记退订并停止</Button>
          </div>}
        </>}
      </section>
    </div>
  </main>;
}
