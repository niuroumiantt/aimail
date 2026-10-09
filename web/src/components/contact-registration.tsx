import { BookUser, Check, ExternalLink, Sparkles, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/data/provider";
import type { ContactRegistrationFields, ContactRegistrationState } from "@/data/types";
import { fullTime } from "@/lib/text";

const labels = {company:"公司／项目", contact:"联系人", email:"联系邮箱", website:"官网", region:"地区", phone:"电话", title:"职位"} as const;
export function ContactRegistration({ threadId }: {threadId: string}) {
  const {contactRegistration, extractContact, saveContact} = useData();
  const [value, setValue] = useState<ContactRegistrationState>();
  const [fields, setFields] = useState<ContactRegistrationFields>();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [identity, setIdentity] = useState<ContactRegistrationState["identity"]>();
  const [checkedLookup, setCheckedLookup] = useState("");
  const dirty = useRef(false);
  const alive = useRef(true);
  const [refresh, setRefresh] = useState(0);
  const merge = (next: ContactRegistrationState) => ({...next.defaults, ...next.suggestion?.fields, contact: next.defaults.contact, email: next.defaults.email, website: next.suggestion?.fields?.website || next.defaults.website});
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await contactRegistration(threadId);
        if (cancelled || busy) return;
        setValue(next);
        if (!dirty.current) setFields(merge(next));
        if (next.registration && !next.registration.receipt.account_id || next.suggestion?.status === "running") timer = setTimeout(() => void poll(), 3000);
      } catch(e) { if (!cancelled) setError((e as Error).message); }
    };
    void poll();
    return () => {cancelled = true; clearTimeout(timer);};
  }, [threadId, contactRegistration, busy, refresh]);
  useEffect(() => () => {alive.current = false;}, []);
  const lookup = fields ? JSON.stringify([fields.company, fields.email, fields.website, fields.company_id]) : "";
  useEffect(() => {
    if (!open || !fields || value?.registration) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void contactRegistration(threadId, fields).then(next => {
        if (!cancelled) {setIdentity(next.identity); setCheckedLookup(lookup);}
      }).catch(e => {if (!cancelled) {setError((e as Error).message); setIdentity(undefined); setCheckedLookup(lookup);}});
    }, 300);
    return () => {cancelled = true; clearTimeout(timer);};
    // Only identity fields trigger lookup; other edits must not discard the selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, lookup, threadId, contactRegistration, Boolean(value?.registration)]);
  const action = async (extract: boolean) => {
    setBusy(true); setError("");
    try {
      const next = extract ? await extractContact(threadId) : await saveContact(threadId, fields!);
      if (!alive.current) return;
      setValue(next);
      if (extract) dirty.current = false;
      else {setOpen(false); setRefresh(v=>v+1);}
    } catch(e) {if (alive.current) setError((e as Error).message);}
    finally {if (alive.current) setBusy(false);}
  };
  const saved = value?.registration;
  const receipt = saved?.receipt;
  const title = saved ? receipt?.account_id ? "已建档" : "已保存 · 等待同步" : "建立档案";
  const checking = open && lookup !== checkedLookup;
  const strong = identity?.matches.filter(v=>v.strong) || [];
  const blocked = !identity?.current || checking || identity?.conflict || strong.length > 0 && !strong.some(v=>v.company_id === fields?.company_id) || !strong.length && !!identity?.matches.length && !fields?.company_id && !fields?.new_company_reason?.trim();
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><button type="button" className="crm-registration-icon" data-saved={!!saved} aria-label={title} title={title} disabled={!fields}>{saved ? <Check size={17} /> : <BookUser size={17} />}</button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-overlay" /><Dialog.Content className="customer-workspace-v2 crm-registration-dialog">
      <header className="crm-dialog-heading"><Dialog.Title>客户档案</Dialog.Title><Dialog.Close asChild><button type="button" className="mail-icon-button" aria-label="关闭客户档案"><X size={17}/></button></Dialog.Close></header>
      <Dialog.Description className="customer-overview-state">公司与联系人统一建档；本次买卖的产品、数量和条件在生意概况及事项跟进中保留。</Dialog.Description>
      {saved ? <><p className="crm-saved"><Check size={16} />{title} · {saved.fields.company || saved.fields.contact || saved.fields.email}</p><p className="customer-overview-state">{saved.fields.contact} · {saved.fields.email}</p>
        {receipt?.account_id ? <a className="crm-link" href={`https://leads.glocalstorage.cn/?lead=${encodeURIComponent(receipt.account_id)}`} target="_blank" rel="noreferrer">查看档案与跟进 <ExternalLink size={14} /></a> : <p className="customer-overview-state">正在同步，刷新不会重复建档。</p>}
      </> : null}
      {error && <p role="alert" className="customer-overview-error">{error}</p>}
      {(error || saved && !receipt?.account_id) && <button type="button" className="crm-action" onClick={() => setRefresh(v => v + 1)}>刷新同步状态</button>}
      {fields && !saved && <form className="crm-form" onSubmit={e=>{e.preventDefault(); if(!blocked)void action(false);}}>
        <button type="button" className="crm-action" disabled={busy || value?.suggestion?.status === "running"} onClick={() => void action(true)}><Sparkles size={14} />{value?.suggestion?.status === "running" ? "正在提取…" : "从邮件提取"}</button>
        {value?.suggestion?.status === "failed" && <p className="customer-overview-error" role="alert">{value.suggestion.error}</p>}
        {value?.suggestion?.fields && <p className="customer-overview-state">{value.suggestion.model} · {value.suggestion.task_version} · {fullTime(value.suggestion.produced_at)} · 邮件 #{value.suggestion.source_id} · AI 建议待核对</p>}
        {value?.suggestion?.stale && <p className="customer-overview-state">话题有新邮件，请重新提取并核对。</p>}
        {value?.suggestion?.warnings?.map(w=><p role="alert" className="customer-overview-error" key={w}>{w}</p>)}
        {Object.entries(labels).map(([key,label])=><label key={key}>{label}<input aria-label={label} type={key==="email"?"email":"text"} required={key==="email"} maxLength={key==="website"?2048:key==="email"?254:["phone","title","region"].includes(key)?100:200} value={String(fields[key as keyof ContactRegistrationFields]??"")} onChange={e=>{dirty.current=true;setFields({...fields,[key]:e.target.value,...(["email","website"].includes(key)?{company_id:null}:{})});}}/>
          {key==="website" && value?.website_inferred && !value.suggestion?.fields?.website && <small>按企业邮箱域名预填，官网尚未核实，可修改。</small>}
          {value?.suggestion?.citations?.[key] && <details><summary>原文依据 · 邮件 #{value.suggestion.citations[key].source_id}</summary><blockquote>{value.suggestion.citations[key].quote}</blockquote></details>}
        </label>)}
        <div className="crm-identity-check" role="status"><strong>公司查重</strong><p>{checking?"正在对照企业邮箱、域名和名称…":!identity?.current?"公司目录暂未同步，请稍后刷新。":identity.conflict?"邮箱和官网匹配到不同公司，请先核实。":identity.matches.length?"发现已有公司，请核实后关联，联系人保存到同一公司。":"未发现同企业邮箱、域名或相似名称的公司。"}</p>
          {!!identity?.matches.length && <label>关联已有公司<select aria-label="关联已有公司" value={fields.company_id||""} onChange={e=>{dirty.current=true;setFields({...fields,company_id:e.target.value||null});}}><option value="">请选择已有公司</option>{identity.matches.map(c=><option key={c.company_id} value={c.company_id}>{c.company} · {c.reasons.join("、")}</option>)}</select></label>}
          {!!identity?.matches.length && !strong.length && !fields.company_id && <label>确认为不同公司的说明<input aria-label="确认为不同公司的说明" maxLength={500} value={fields.new_company_reason||""} onChange={e=>setFields({...fields,new_company_reason:e.target.value})}/></label>}
        </div>
        <button type="submit" className="crm-action crm-primary" disabled={busy || !fields.email || blocked}>{busy?"正在保存…":fields.company_id?"确认关联并保存联系人":"确认建档并同步"}</button>
      </form>}
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}
