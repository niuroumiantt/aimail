import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

type State = { thread_id: number; owner: string; pending: string; version: number; summary: string; note: string; subject?: string; unread_count?: number };
type Detail = { state: State | null; unresolved_send: {id:number;sender:string;state:string;created_at:string}|null; last_message_id: number; thread: { subject: string; messages: {id:string;from_email:string;sent_at:string;body:string;quoted:string|null}[] }; history: { id: number; actor: string; action: string; at: string }[] };
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", "X-Mailbox-Address": localStorage.getItem("mailbox-address") ?? "" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === "string" ? error.detail : "跟进服务未启用或请求失败"); }
  return response.json();
}

export function FollowupWorkspace() {
  const { id } = useParams();
  return <FollowupView key={id ?? 'list'} />;
}

function FollowupView() {
  const { id } = useParams();
  const [list, setList] = useState<{ items: State[]; members: string[]; identity: string }>({items:[],members:[],identity:''});
  const [detail, setDetail] = useState<Detail | null>(null);
  const [recipient, setRecipient] = useState(''); const [note, setNote] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState('');
  const [preview, setPreview] = useState<{token:string;sender:string;recipient:string;body:string;subject:string} | null>(null);
  const [sendResult, setSendResult] = useState('');
  const [localUncertain, setUncertain] = useState(false);
  const uncertain = localUncertain || !!detail?.unresolved_send;
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
  async function markRead() {
    if (!id || !detail) return;
    setBusy(true);
    try { await api(`/api/followups/${id}/read`, {last_message_id:detail.last_message_id}); await refresh(); }
    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function prepareReply() {
    if (!id || !detail || !reply.trim()) return;
    setBusy(true); setError('');
    try {
      const info = await api<{token:string;sender:string;recipient:string}>(`/api/followups/${id}/reply-token`, {});
      setPreview({...info, body:reply, subject:`Re: ${detail.thread.subject}`});
    } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function sendReply() {
    if (!id || !preview) return;
    setBusy(true); setError('');
    try {
      await api(`/api/followups/${id}/reply`, preview);
      setReply(''); setPreview(null); setSendResult('邮件已提交发送，请在历史中核对；不代表客户已收到。');
      await refresh();
    } catch {
      setUncertain(true); setPreview(null);
      setError('发送结果需核对，请检查个人邮箱已发送记录，暂勿重复发送。');
    } finally { setBusy(false); }
  }
  const summary = state ? JSON.parse(state.summary) as Record<string,unknown> : null;
  return <main className="mx-auto max-w-5xl space-y-5 p-6 text-ink">
    <header className="flex gap-6"><Link to="/">返回邮箱</Link><Link to="/followups">我的跟进</Link><button onClick={() => void refresh()}>刷新</button></header>
    <h1 className="text-xl font-semibold">aimail · 销售交接</h1>
    {error && <p role="alert">{error}</p>}
    {!id && <ul>{list.items.map(item => <li key={item.thread_id}><Link to={`/followups/${item.thread_id}`}>{item.subject}</Link> · {item.pending ? `等待 ${item.pending} 接手` : `负责人：${item.owner}`} · {item.unread_count ? `${item.unread_count} 封未读来信` : '无未读来信'}</li>)}</ul>}
    {!id && !error && !list.items.length && <p>暂无交接记录。打开邮件会话后选择“分配 / 转交”。</p>}
    {detail && <section className="space-y-4"><h2>{detail.thread.subject}</h2><p>当前负责人：{state?.owner ?? list.identity}；待接手：{state?.pending || '无'}</p>
      {summary && <article className="border border-line p-4"><h3>AI 阶段总结 · 需结合原文核对</h3>{([['stage','当前阶段'],['needs','客户需求'],['commitments','已作承诺'],['open_questions','待解决事项'],['next_steps','建议下一步'],['model','模型'],['source_ids','引用邮件']] as const).map(([key,label]) => <p className="my-2 whitespace-pre-wrap" key={key}>{label}：{String(summary[key] ?? '')}</p>)}</article>}
      {state?.note && <p>交接说明：{state.note}</p>}
      {detail.unresolved_send && <aside role="alert" className="border border-line p-4"><h3>发送结果待核对，已暂停重复发送</h3><p>{detail.unresolved_send.created_at} · {detail.unresolved_send.sender}</p><p>请核对个人邮箱或邮件服务商的投递记录。没有找到“已发送”副本不能证明未发送；不要直接重发。</p>{(!state || state.owner === list.identity) && <a href={`/api/followups/${id}/unresolved.eml`}>下载待核对原邮件（含 Message-ID）</a>}</aside>}
      <section className="space-y-3"><h3>邮件往来原文</h3>{detail.thread.messages.map(message => <article key={message.id} className="border border-line p-4"><p>{message.from_email} · {message.sent_at}</p><p className="whitespace-pre-wrap">{message.body}</p>{message.quoted && <details><summary>引用历史</summary><p className="whitespace-pre-wrap">{message.quoted}</p></details>}</article>)}<button disabled={busy} onClick={() => void markRead()}>将当前显示的邮件标为已读</button></section>
      <a href={`/api/followups/${id}/history.zip`}>下载完整邮件历史及附件（原始邮件压缩包）</a><p>仅交接当前会话；下载不会发送邮件。</p>
      {state?.pending === list.identity && <button disabled={busy} onClick={() => void act('accept')}>确认接手</button>}
      {state?.pending && state.owner === list.identity && <button disabled={busy} onClick={() => void act('cancel')}>取消交接</button>}
      {(!state || state.owner === list.identity) && <section className="space-y-3 border border-line p-4"><h3>用我的个人邮箱回复</h3><textarea className="block w-full border border-line p-2" aria-label="回复正文" value={reply} maxLength={100000} disabled={busy || uncertain || !!preview} onChange={e => setReply(e.target.value)} /><button disabled={busy || uncertain || !reply.trim() || !!preview} onClick={() => void prepareReply()}>核对发件身份与内容</button>{preview && <div><p>发件人：{preview.sender}</p><p>收件人：{preview.recipient}</p><p>主题：{preview.subject}</p><pre className="whitespace-pre-wrap">{preview.body}</pre><button disabled={busy} onClick={() => void sendReply()}>确认发送这封邮件</button><button disabled={busy} onClick={() => setPreview(null)}>返回修改</button></div>}{sendResult && <p role="status">{sendResult}</p>}</section>}
      {(!state || (state.owner === list.identity && !state.pending)) && <div className="space-y-3 border border-line p-4"><label>交给销售 <select aria-label="接收销售" value={recipient} onChange={e => setRecipient(e.target.value)}><option value="">请选择</option>{list.members.filter(x => x !== list.identity).map(x => <option key={x}>{x}</option>)}</select></label><textarea className="block w-full border border-line p-2" aria-label="交接说明" value={note} onChange={e => setNote(e.target.value)} maxLength={4000}/><button disabled={busy || !recipient} onClick={() => void act('offer')}>{busy ? '正在处理…' : '生成 AI 总结并提交交接'}</button></div>}
      <h3>交接记录</h3><ul>{detail.history.map(e => <li key={e.id}>{e.at} · {e.actor} · {({offer:'发起交接',accept:'确认接手',cancel:'取消交接'} as Record<string,string>)[e.action] ?? e.action}</li>)}</ul>
    </section>}
  </main>;
}
