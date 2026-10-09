import { BookUser, Check, ExternalLink, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/data/provider";
import type { ContactRegistrationFields, ContactRegistrationState } from "@/data/types";
import { fullTime } from "@/lib/text";

const labels: Partial<Record<keyof ContactRegistrationFields, string>> = {
  company:"公司／项目", contact:"联系人", email:"联系邮箱", website:"官网", region:"地区",
  phone:"电话", title:"职位", products:"产品分类", wants:"采购／供货需求", quantity:"数量", terms:"价格／交期及条件", next_step:"下一步", due_at:"跟进日期",
};
export function ContactRegistration({ threadId }: {threadId: string}) {
  const {contactRegistration, extractContact, saveContact} = useData();
  const [value, setValue] = useState<ContactRegistrationState>();
  const [fields, setFields] = useState<ContactRegistrationFields>();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dirty = useRef(false);
  const alive = useRef(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await contactRegistration(threadId);
        if (cancelled || busy) return;
        setValue(next); setError("");
        if (!dirty.current) setFields({...next.defaults, ...next.suggestion?.fields});
        if (next.registration && Object.keys(next.registration.receipt).length === 0 || next.suggestion?.status === "running") timer = setTimeout(() => void poll(), 3000);
      } catch(e) { if (!cancelled) setError((e as Error).message); }
    };
    void poll();
    return () => {cancelled = true; clearTimeout(timer);};
  }, [threadId, contactRegistration, busy, refresh]);
  useEffect(() => () => {alive.current = false;}, []);
  const action = async (extract: boolean) => {
    setBusy(true); setError("");
    try {
      const next = extract ? await extractContact(threadId) : await saveContact(threadId, fields!);
      if (!alive.current) return;
      setValue(next);
      if (extract) dirty.current = false;
      else setOpen(false);
    } catch(e) {if (alive.current) setError((e as Error).message);}
    finally {if (alive.current) setBusy(false);}
  };
  const saved = value?.registration;
  const receipt = saved?.receipt;
  return <section className="customer-business-overview crm-registration" aria-label="客户建档">
    <header><div className="customer-section-label"><BookUser size={16} /><h3>客户档案</h3></div>
      {!saved && <button type="button" className="crm-action" onClick={() => setOpen(v => !v)} disabled={!fields}>{open ? "收起" : "建立档案"}</button>}
    </header>
    {saved ? <><p className="crm-saved"><Check size={16} />{receipt?.account_id ? "已建档" : "已保存 · 等待同步"} · {saved.fields.company || saved.fields.contact || saved.fields.email}</p>
      <p className="customer-overview-state">{saved.fields.products || "产品分类待补充"} · {saved.fields.email}</p>
      {receipt?.account_id ? <a className="crm-link" href={`https://leads.glocalstorage.cn/?lead=${encodeURIComponent(receipt.account_id)}`} target="_blank" rel="noreferrer">查看档案与跟进 <ExternalLink size={14} /></a> : <p className="customer-overview-state">正在同步客户工作台；刷新或重复点击不会重复建档。长时间未完成请联系管理员。</p>}
    </> : <p className="customer-overview-state">保存公司、联系人和本次需求，统一查询与跟进。</p>}
    {error && <p role="alert" className="customer-overview-error">{error}</p>}
    {(error || saved && !receipt?.account_id) && <button type="button" className="crm-action" onClick={() => setRefresh(v => v + 1)}>刷新同步状态</button>}
    {open && fields && !saved && <form className="crm-form" onSubmit={e => {e.preventDefault(); void action(false);}}>
      <p className="customer-overview-state">预填只读取本话题最近的邮件文本（最多 4 万字），不读取附件；请核对引用依据。</p>
      <button type="button" className="crm-action" disabled={busy || value?.suggestion?.status === "running"} onClick={() => void action(true)}><Sparkles size={14} />{value?.suggestion?.status === "running" ? "正在提取…" : "从邮件提取预填"}</button>
      {value?.suggestion?.status === "failed" && <p className="customer-overview-error" role="alert">{value.suggestion.error}</p>}
      {value?.suggestion?.fields && <><p className="customer-overview-state">{value.suggestion.model} · {value.suggestion.task_version} · {fullTime(value.suggestion.produced_at)} · 邮件 #{value.suggestion.source_id} · AI 建议待核对</p>
        <button type="button" className="crm-action" onClick={() => {setFields({...value.defaults,...value.suggestion?.fields}); dirty.current = false;}}>重新使用预填内容</button></>}
      {value?.suggestion?.stale && <p className="customer-overview-state">话题有新邮件，请重新提取并核对。</p>}
      {value?.suggestion?.warnings?.map(w => <p role="alert" className="customer-overview-error" key={w}>{w}</p>)}
      {!!value?.candidates.length && <label>关联已建公司<select aria-label="关联已建公司" value={fields.link_registration_id ?? ""} onChange={e => {dirty.current = true; setFields({...fields,link_registration_id:e.target.value ? Number(e.target.value) : null});}}><option value="">新建独立公司档案</option>{value.candidates.map(c => <option key={c.id} value={c.id}>{c.company}（相同联系人，需核实）</option>)}</select></label>}
      {Object.entries(labels).map(([key,label]) => <label key={key}>{label}
        {key === "wants" || key === "terms" ? <textarea aria-label={label} value={String(fields[key as keyof ContactRegistrationFields] ?? "")} maxLength={key === "wants" ? 2000 : 1000} onChange={e => {dirty.current=true;setFields({...fields,[key]:e.target.value});}} /> : <input aria-label={label} type={key === "email" ? "email" : key === "due_at" ? "date" : "text"} required={key === "email"} maxLength={key === "website" ? 2048 : key === "next_step" ? 500 : key === "products" ? 300 : key === "email" ? 254 : ["phone","title","region"].includes(key) ? 100 : 200} value={String(fields[key as keyof ContactRegistrationFields] ?? "")} onChange={e => {dirty.current=true;setFields({...fields,[key]:e.target.value});}} />}
        {value?.suggestion?.citations?.[key] && <details><summary>查看原文依据 · 邮件 #{value.suggestion.citations[key].source_id}</summary><blockquote>{value.suggestion.citations[key].quote}</blockquote></details>}
      </label>)}
      <label>业务关系<select aria-label="业务关系" value={fields.business_role} onChange={e=>{dirty.current=true;setFields({...fields,business_role:e.target.value as ContactRegistrationFields["business_role"]});}}><option value="unknown">待核实</option><option value="buyer">买方</option><option value="supplier">供应商</option><option value="both">双方</option></select></label>
      <label>线索来源<select aria-label="线索来源" value={fields.source_type} onChange={e=>{dirty.current=true;setFields({...fields,source_type:e.target.value as ContactRegistrationFields["source_type"]});}}><option value="manual">其他／待核实</option><option value="inbound_purchase">采购来信</option><option value="inbound_supply">供货来信</option><option value="outbound">我方主动开发</option></select></label>
      <label>本次事项<select aria-label="本次事项" value={fields.intent} onChange={e=>{dirty.current=true;setFields({...fields,intent:e.target.value as ContactRegistrationFields["intent"]});}}><option value="contact">仅建立联系</option><option value="purchase">采购需求</option><option value="supply">供货机会</option></select></label>
      <p className="customer-overview-state">核对后保存为人工确认资料。公司未明确可留空；不会自动发信。</p>
      <button type="submit" className="crm-action crm-primary" disabled={busy || !fields.email}>{busy ? "正在保存…" : "确认建档并同步"}</button>
    </form>}
  </section>;
}
