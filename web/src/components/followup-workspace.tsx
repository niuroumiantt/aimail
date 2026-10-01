import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Alert, Avatar, Badge, Button, Card, Collapse, ConfigProvider, Descriptions, Empty, Input, Modal, Select, Skeleton, Space, Tag, Timeline } from "antd";
import zhCN from "antd/locale/zh_CN";
import { ArrowLeft, ArrowUpRight, Check, Download, Inbox, Mail, RefreshCw, Search, Send, Sparkles, Undo2 } from "lucide-react";
import "@/tokens/followup-workspace.css";
import { FOLLOWUP_PRIMARY, followupTheme } from "@/tokens/followup-theme";
import { AccountMenu } from "@/components/account-menu";

type State = { thread_id: number; owner: string; pending: string; version: number; summary: string; note: string; subject?: string; unread_count?: number; assignment_authority?: "aimail" | "leadsgen"; assignment_account_id?: string };
type FollowupList = { items: State[]; members: string[]; identity: string };
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
  const navigate = useNavigate();
  const { id } = useParams();
  const [list, setList] = useState<FollowupList>({items:[],members:[],identity:''});
  const [detail, setDetail] = useState<Detail | null>(null);
  const [recipient, setRecipient] = useState(''); const [note, setNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState('');
  const [preview, setPreview] = useState<{token:string;sender:string;recipient:string;body:string;subject:string} | null>(null);
  const [sendResult, setSendResult] = useState('');
  const [resolutionOutcome, setResolutionOutcome] = useState<''|'sent'|'not_sent'>('');
  const [resolutionEvidence, setResolutionEvidence] = useState('');
  const [resolutionResult, setResolutionResult] = useState('');
  const [localUncertain, setUncertain] = useState(false);
  const uncertain = localUncertain || !!detail?.unresolved_send;
  const refreshFollowups = useCallback(async () => {
    try { setList(await api<FollowupList>('/api/followups')); setError(''); }
    catch(e) { setError((e as Error).message); }
  }, []);
  const refresh = useCallback(async () => {
    try { setList(await api('/api/followups')); setDetail(id ? await api(`/api/followups/${id}`) : null); setError(''); }
    catch(e) { setError((e as Error).message); setDetail(null); } finally { setLoading(false); }
  }, [id]);
  useEffect(() => { const timer = setTimeout(() => void refresh(), 0); return () => clearTimeout(timer); }, [refresh]);
  useEffect(() => {
    if (id) return;
    const refresh = () => { void refreshFollowups(); };
    const timer = setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [id, refreshFollowups]);
  async function act(action: string, reason = "") {
    if (!detail || !id) return;
    setBusy(true); setError('');
    try { await api(`/api/followups/${id}/${action}`, {version:detail.state?.version ?? 0,recipient,note,reason}); setReturnOpen(false); if (action === 'decline') navigate('/followups'); else await refresh(); }
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
  async function resolveSend() {
    if (!id || !detail?.unresolved_send || !resolutionOutcome || resolutionEvidence.trim().length < 6) return;
    setBusy(true); setError('');
    try {
      await api(`/api/followups/${id}/unresolved/${detail.unresolved_send.id}/resolve`, {outcome:resolutionOutcome,evidence_reference:resolutionEvidence});
      setUncertain(false);
      setResolutionResult(resolutionOutcome === 'sent' ? '已根据服务商证据记录为已发送；系统没有发送邮件。' : '已根据服务商证据记录为未发送；系统没有重试。请人工检查内容后再决定是否新建发送。');
      setResolutionOutcome(''); setResolutionEvidence('');
      await refresh();
    } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const summary = parseSummary(state?.summary);
  const visible = list.items.filter(item => (!query || `${item.subject} ${item.owner} ${item.pending}`.toLowerCase().includes(query.toLowerCase())) && (filter !== 'pending' || item.pending === list.identity) && (filter !== 'unread' || !!item.unread_count));
  const canReply = !state || state.owner === list.identity;
  const managedByLeads = state?.assignment_authority === 'leadsgen';
  const canOffer = !managedByLeads && (!state || (state.owner === list.identity && !state.pending));
  return <ConfigProvider locale={zhCN} theme={followupTheme}>
    <div className="followup-shell">
      <div className="followup-topbar"><Link to="/" className="followup-brand"><span><Mail size={21}/></span><strong>aimail</strong><small>销售工作台</small></Link><AccountMenu/></div>
      <main className="followup-main">
        <div className="followup-page-heading"><div><div className="followup-eyebrow">SALES WORKSPACE</div><h1>我的跟进</h1><p>接手客户线索，把每一次往来推进到下一步。</p></div><Space wrap><Button href="https://leads.glocalstorage.cn/" icon={<ArrowUpRight size={16}/>}>线索平台</Button><Button icon={<RefreshCw size={16}/>} disabled={busy} onClick={()=>void refresh()}>刷新</Button></Space></div>
        {error && <Alert className="followup-alert" type="error" showIcon title={error}/>}
        <div className="followup-metrics">{[['我的交接',list.items.length],['待我接手',list.items.filter(i=>i.pending===list.identity).length],['未读来信',list.items.reduce((n,i)=>n+(i.unread_count??0),0)]].map(([label,value])=><div className="followup-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
        <div className={`followup-grid ${id?'has-selection':''}`}>
          <aside className="followup-list" aria-label="交接任务列表"><div className="followup-list-heading"><h2>交接任务 <span>{list.items.length}</span></h2><Input aria-label="搜索交接任务" placeholder="搜索主题或负责人" prefix={<Search size={16}/>} value={query} onChange={e=>setQuery(e.target.value)} allowClear/><div className="followup-filter">{[['all','全部'],['pending','待接手'],['unread','未读']].map(([key,label])=><Button key={key} size="small" type={filter===key?'primary':'text'} onClick={()=>setFilter(key)}>{label}</Button>)}</div></div>
            {loading ? <div className="followup-list-loading"><Skeleton active/></div> : visible.length ? <nav className="followup-task-list">{visible.map(item=><Link key={item.thread_id} to={`/followups/${item.thread_id}`} className={`followup-task ${String(item.thread_id)===id?'is-selected':''}`} aria-current={String(item.thread_id)===id?'page':undefined}><div className="followup-task-top"><Tag color={item.pending?'gold':'green'}>{item.pending?'待接手':'跟进中'}</Tag>{!!item.unread_count&&<Badge count={item.unread_count} color={FOLLOWUP_PRIMARY}/>}</div><h3>{item.subject||'未命名邮件会话'}</h3><p>{item.pending?`等待 ${item.pending} 接手`:`负责人：${item.owner}`}</p><span className="followup-task-unread" role="status">{item.unread_count?`${item.unread_count} 封未读来信`:'无未读来信'}</span></Link>)}</nav> : <Empty className="followup-list-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description={query||filter!=='all'?'没有符合条件的任务':'暂无交接记录'}/>}
          </aside>
          <section className="followup-detail" aria-label="交接详情">
            {loading&&id ? <Card><Skeleton active paragraph={{rows:8}}/></Card> : detail ? <>
              <div className="followup-detail-header"><Link to="/followups" className="followup-back"><ArrowLeft size={16}/>返回任务列表</Link><div className="followup-subject"><Avatar size={44} icon={<Mail size={22}/>}/><div><Tag color={state?.pending?'gold':'green'}>{state?.pending?'等待接手':'正在跟进'}</Tag><h2>{detail.thread.subject}</h2><p>当前负责人：{state?.owner??list.identity}</p>{state?.pending&&<p>待接手：{state.pending}</p>}</div></div><div className="followup-actions">{state?.pending===list.identity&&<><Button type="primary" icon={<Check size={16}/>} loading={busy} onClick={()=>void act('accept')}>确认接手</Button><Button icon={<Undo2 size={16}/>} disabled={busy} onClick={()=>setReturnOpen(true)}>退回</Button></>}{state?.pending&&state.owner===list.identity&&<Button disabled={busy} onClick={()=>void act('cancel')}>取消交接</Button>}<Button href={`/api/followups/${id}/history.zip`} icon={<Download size={16}/>}>下载邮件及附件</Button></div></div>
              <div className="followup-detail-body">
                <Card className="followup-summary" title={<Space><Sparkles size={17}/>交接摘要</Space>} extra={<Tag color="blue">结合原文核对</Tag>}>{summary&&['stage','needs','commitments','open_questions','next_steps'].some(key=>summary[key]) ? <div className="followup-summary-grid">{([['stage','当前阶段'],['needs','客户需求'],['commitments','已作承诺'],['open_questions','待确认事项'],['next_steps','建议下一步']] as const).filter(([key])=>summary[key]).map(([key,label])=><div key={key}><h3>{label}</h3><p>{summaryText(summary[key])}</p></div>)}</div> : <p className="followup-muted">尚未生成交接摘要，请先查看下面的邮件原文。</p>}{state?.note&&!managedByLeads&&<div className="followup-handoff-note"><strong>交接说明</strong><p>{state.note}</p></div>}</Card>
                {detail.unresolved_send&&<Card title="发送结果待核对，已暂停重复发送"><Alert type="warning" showIcon title="请先核对邮件服务商的投递记录" description="找不到已发送副本不能证明未发送。只有服务商明确确认结果后，才能记录；此处不会发送或重试邮件。"/><p>{formatTime(detail.unresolved_send.created_at)} · {detail.unresolved_send.sender}</p>{canReply&&<div className="followup-form"><Button href={`/api/followups/${id}/unresolved.eml`}>下载待核对原邮件（含 Message-ID）</Button><label>核对结果<Select aria-label="核对结果" value={resolutionOutcome||undefined} placeholder="请选择服务商确认结果" onChange={setResolutionOutcome} options={[{value:'sent',label:'服务商确认已接受发送'},{value:'not_sent',label:'服务商确认未接受发送'}]}/></label><label>服务商核对依据<Input aria-label="服务商核对依据" maxLength={500} value={resolutionEvidence} onChange={e=>setResolutionEvidence(e.target.value)} placeholder="投递日志编号或服务商记录号"/></label><Button disabled={busy||!resolutionOutcome||resolutionEvidence.trim().length<6} onClick={()=>void resolveSend()}>记录核对结果（不发送邮件）</Button></div>}</Card>}
                {resolutionResult&&<Alert type="success" showIcon title={resolutionResult}/>}
                <Card title="邮件往来" extra={<Button size="small" disabled={busy} onClick={()=>void markRead()}>将当前显示的邮件标为已读</Button>}><div>{detail.thread.messages.map(message=><article key={message.id} className="followup-message"><div className="followup-message-meta"><Avatar size={32}>{message.from_email.slice(0,1).toUpperCase()}</Avatar><div><strong>{message.from_email}</strong><time>{formatTime(message.sent_at)}</time></div></div><div className="followup-message-body">{message.body}</div>{message.quoted&&<Collapse size="small" ghost items={[{key:message.id,label:'展开引用历史',children:<div className="followup-message-body followup-quoted">{message.quoted}</div>}]}/>}</article>)}</div></Card>
                {canReply&&<Card title={<Space><Send size={17}/>用我的个人邮箱回复</Space>}><div className="followup-form"><Input.TextArea aria-label="回复正文" placeholder="输入回复内容，发送前会再次核对发件人和收件人…" autoSize={{minRows:5,maxRows:16}} value={reply} maxLength={100000} disabled={busy||uncertain||!!preview} onChange={e=>setReply(e.target.value)}/><Button type="primary" disabled={busy||uncertain||!reply.trim()||!!preview} onClick={()=>void prepareReply()}>核对发件身份与内容</Button>{sendResult&&<Alert type="success" showIcon title={sendResult}/>}</div></Card>}
                {managedByLeads&&<Alert type="info" title="负责人在客户工作台统一管理" description={<a href={`https://leads.glocalstorage.cn/?lead=${encodeURIComponent(state?.assignment_account_id ?? '')}`}>前往客户工作台</a>}/>}
                {canOffer&&<Card title="转交给销售同事"><div className="followup-form"><label>接收销售<Select aria-label="接收销售" value={recipient||undefined} onChange={setRecipient} placeholder="选择接收同事" options={list.members.filter(x=>x!==list.identity).map(value=>({value,label:value}))}/></label><label>交接说明<Input.TextArea aria-label="交接说明" placeholder="补充客户背景、待确认问题和建议下一步…" autoSize={{minRows:3,maxRows:8}} value={note} onChange={e=>setNote(e.target.value)} maxLength={4000}/></label><Button type="primary" disabled={busy||!recipient} onClick={()=>void act('offer')}>{busy?'正在处理…':'生成 AI 总结并提交交接'}</Button><p className="followup-muted">交接后，此会话的自动开发信会暂停；取消交接不会自动恢复发送。</p></div></Card>}
                <Card title="交接记录">{detail.history.length ? <Timeline items={detail.history.map(event=>({key:event.id,children:<div><strong>{({offer:'发起交接',accept:'确认接手',cancel:'取消交接',decline:'退回交接'} as Record<string,string>)[event.action]??event.action}</strong><p>{event.actor}</p><time>{formatTime(event.at)}</time></div>}))}/> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无交接记录"/>}</Card>
              </div>
            </> : <div className="followup-welcome"><div className="followup-welcome-icon"><Inbox size={32}/></div><h2>{id?'暂时无法打开这条交接':'从左侧选择一条交接任务'}</h2><p>{id?'请刷新或返回任务列表，查看你有权限的记录。':'先看客户摘要，再接手、回复或安排下一步。'}</p><Button href="https://leads.glocalstorage.cn/">查看我的线索</Button></div>}
          </section>
        </div>
      </main>
    </div>
    <Modal title="退回这条交接" open={returnOpen} onCancel={()=>setReturnOpen(false)} okText="确认退回" cancelText="取消" confirmLoading={busy} okButtonProps={{disabled:!returnReason.trim()}} onOk={()=>void act('decline',returnReason.trim())}><p>说明退回原因，便于负责人重新安排。</p><Input.TextArea aria-label="退回原因" value={returnReason} onChange={e=>setReturnReason(e.target.value)} maxLength={1000} autoSize={{minRows:3,maxRows:8}}/></Modal>
    <Modal title="核对并发送回复" open={!!preview} onCancel={()=>{if(!busy)setPreview(null);}} footer={<Space><Button disabled={busy} onClick={()=>setPreview(null)}>返回修改</Button><Button type="primary" loading={busy} onClick={()=>void sendReply()}>确认发送这封邮件</Button></Space>}>{preview&&<><Descriptions column={1} items={[{key:'sender',label:'发件人',children:preview.sender},{key:'recipient',label:'收件人',children:preview.recipient},{key:'subject',label:'主题',children:preview.subject}]}/><div className="followup-reply-preview">{preview.body}</div></>}</Modal>
  </ConfigProvider>;
}
function parseSummary(raw?:string):Record<string,unknown>|null { if(!raw)return null; try { const value:unknown=JSON.parse(raw); return value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{needs:typeof value==='string'?value:raw}; } catch { return {needs:raw}; } }
function summaryText(value:unknown):string { return Array.isArray(value)?value.map(summaryText).join('\n'):typeof value==='object'&&value!==null?JSON.stringify(value):String(value??''); }
function formatTime(value:string):string { const date=new Date(value); return Number.isNaN(date.getTime())?value:date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}); }
