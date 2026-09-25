import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

type State = { thread_id: number; owner: string; pending: string; version: number; summary: string; note: string; subject?: string };
type Detail = { state: State | null; thread: { subject: string }; history: { id: number; actor: string; action: string; at: string }[] };
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", "X-Mailbox-Address": localStorage.getItem("mailbox-address") ?? "" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === "string" ? error.detail : "跟进服务未启用或请求失败"); }
  return response.json();
}

export function FollowupWorkspace() {
  const { id } = useParams();
  const [list, setList] = useState<{ items: State[]; members: string[]; identity: string }>({items:[],members:[],identity:''});
  const [detail, setDetail] = useState<Detail | null>(null);
  const [recipient, setRecipient] = useState(''); const [note, setNote] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { setList(await api('/api/followups')); setDetail(id ? await api(`/api/followups/${id}`) : null); setError(''); }
    catch(e) { setError((e as Error).message); setDetail(null); }
  }, [id]);
  useEffect(() => { const timer = setTimeout(() => void refresh(), 0); return () => clearTimeout(timer); }, [refresh]);
  async function act(action: string) {
    if (!detail || !id) return;
    setBusy(true);
    try { await api(`/api/followups/${id}/${action}`, {version:detail.state?.version ?? 0,recipient,note}); await refresh(); }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const state = detail?.state;
  const summary = state ? JSON.parse(state.summary) as Record<string,unknown> : null;
  return <main className="mx-auto max-w-5xl space-y-5 p-6 text-ink">
    <header className="flex gap-6"><Link to="/">返回邮箱</Link><Link to="/followups">我的跟进</Link><button onClick={() => void refresh()}>刷新</button></header>
    <h1 className="text-xl font-semibold">aimail · 销售交接</h1>
    {error && <p role="alert">{error}</p>}
    {!id && <ul>{list.items.map(item => <li key={item.thread_id}><Link to={`/followups/${item.thread_id}`}>{item.subject}</Link> · {item.pending ? `等待 ${item.pending} 接手` : `负责人：${item.owner}`}</li>)}</ul>}
    {!id && !error && !list.items.length && <p>暂无交接记录。打开邮件会话后选择“分配 / 转交”。</p>}
    {detail && <section className="space-y-4"><h2>{detail.thread.subject}</h2><p>当前负责人：{state?.owner ?? list.identity}；待接手：{state?.pending || '无'}</p>
      {summary && <article className="border border-line p-4"><h3>AI 阶段总结 · 需结合原文核对</h3>{([['stage','当前阶段'],['needs','客户需求'],['commitments','已作承诺'],['open_questions','待解决事项'],['next_steps','建议下一步'],['model','模型'],['source_ids','引用邮件']] as const).map(([key,label]) => <p className="my-2 whitespace-pre-wrap" key={key}>{label}：{String(summary[key] ?? '')}</p>)}</article>}
      {state?.note && <p>交接说明：{state.note}</p>}
      <a href={`/api/followups/${id}/history.zip`}>下载完整邮件历史及附件（原始邮件压缩包）</a><p>仅交接当前会话；下载不会发送邮件。</p>
      {state?.pending === list.identity && <button disabled={busy} onClick={() => void act('accept')}>确认接手</button>}
      {state?.pending && state.owner === list.identity && <button disabled={busy} onClick={() => void act('cancel')}>取消交接</button>}
      {(!state || (state.owner === list.identity && !state.pending)) && <div className="space-y-3 border border-line p-4"><label>交给销售 <select aria-label="接收销售" value={recipient} onChange={e => setRecipient(e.target.value)}><option value="">请选择</option>{list.members.filter(x => x !== list.identity).map(x => <option key={x}>{x}</option>)}</select></label><textarea className="block w-full border border-line p-2" aria-label="交接说明" value={note} onChange={e => setNote(e.target.value)} maxLength={4000}/><button disabled={busy || !recipient} onClick={() => void act('offer')}>{busy ? '正在处理…' : '生成 AI 总结并提交交接'}</button></div>}
      <h3>交接记录</h3><ul>{detail.history.map(e => <li key={e.id}>{e.at} · {e.actor} · {({offer:'发起交接',accept:'确认接手',cancel:'取消交接'} as Record<string,string>)[e.action] ?? e.action}</li>)}</ul>
    </section>}
  </main>;
}
