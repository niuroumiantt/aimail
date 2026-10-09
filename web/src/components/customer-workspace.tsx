import { RefreshCw, Sparkles, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CustomerContext, Thread } from "@/data/types";
import { fullTime } from "@/lib/text";
import { ContactRegistration } from "./contact-registration";
import { Avatar } from "./avatar";
import "@/tokens/customer-workspace.css";

export function CustomerWorkspace({ thread, mailbox, revision, load, refresh }: {
  thread: Thread; mailbox: string; revision: string;
  load: (id: string) => Promise<CustomerContext>;
  refresh: (id: string, retry?: boolean) => Promise<{ queued: number }>;
}) {
  const scope = `${mailbox}:${thread.id}:${thread.email}`;
  const [result, setResult] = useState<{ scope: string; value: CustomerContext }>();
  const [error, setError] = useState<{ scope: string; text: string }>();
  const [retry, setRetry] = useState(0);
  const previousRetry = useRef(0);
  const context = result?.scope === scope ? result.value : undefined;
  const currentError = error?.scope === scope ? error.text : undefined;
  const project = context?.projects.find(value => value.id === thread.id);
  const summary = project?.summary;
  const latest = project?.updated_at;
  const domain = thread.email.split("@")[1] ?? "";
  // The API's legacy company field contains a domain prefix, not a verified company.
  const company = thread.company && thread.company.toLowerCase() !== domain.split(".")[0]?.toLowerCase()
    ? thread.company : "";

  useEffect(() => {
    const explicitRetry = retry !== previousRetry.current;
    previousRetry.current = retry;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const publish = (value: CustomerContext) => {
      if (alive) { setResult({ scope, value }); setError(undefined); }
    };
    const continuePolling = (value: CustomerContext) => {
      const current = value.projects.find(value => value.id === thread.id);
      if (alive && current?.state === "running" && Date.now() - started < 600_000) {
        timer = setTimeout(() => void poll(), 2000);
      }
    };
    const poll = async () => {
      try {
        const value = await load(thread.id);
        if (!alive) return;
        publish(value);
        continuePolling(value);
      } catch (e) { if (alive) setError({ scope, text: e instanceof Error ? e.message : String(e) }); }
    };
    void (async () => {
      try {
        let value = await load(thread.id);
        if (!alive) return;
        publish(value);
        const current = value.projects.find(value => value.id === thread.id);
        if (value.configured && current && current.state !== "running" &&
          (explicitRetry || current.state === "none" || current.stale && current.state !== "failed")) {
          await refresh(thread.id, explicitRetry);
          if (!alive) return;
          value = await load(thread.id);
          if (!alive) return;
          publish(value);
        }
        continuePolling(value);
      } catch (e) { if (alive) setError({ scope, text: e instanceof Error ? e.message : String(e) }); }
    })();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [scope, thread.id, revision, load, refresh, retry]);

  return <div className="customer-workspace-v2">
    <section className="customer-introduction" aria-label="客户介绍">
      <div className="customer-section-label"><UserRound size={15} aria-hidden /><span>客户介绍</span></div>
      <div className="customer-identity"><Avatar name={thread.contact} size="lg" muted /><div><h2>{thread.contact || thread.email}</h2>{company && <p>{company}</p>}</div></div>
      <dl className="customer-contact-facts">
        <div><dt>邮箱</dt><dd>{thread.email}</dd></div>
        {thread.region && <div><dt>地区</dt><dd>{thread.region}</dd></div>}
        {!company && domain && <div><dt>邮箱域名</dt><dd>{domain}</dd></div>}
      </dl>
    </section>
    <ContactRegistration key={`${mailbox}:${thread.id}`} threadId={thread.id} />
    <section className="customer-business-overview" aria-label="当前话题的生意概况">
      <header><div className="customer-section-label"><Sparkles size={16} aria-hidden /><h3>生意概况</h3></div><button
        type="button" className="mail-icon-button" title="更新当前话题；内容未变化时复用已有概况"
        aria-label="更新当前话题的生意概况" disabled={!context?.configured && !currentError || project?.state === "running"}
        onClick={() => setRetry(value => value + 1)}><RefreshCw size={16} /></button></header>
      <div className="customer-current-topic"><span>当前话题</span><h4>{project?.subject || thread.subject}</h4>
        {project && <p>{project.scope.total} 封往来 · 来信与我方回复</p>}
        {latest && <p className="customer-latest-mail">{summary && !project?.stale ? "截至" : "最新往来"} <time dateTime={latest}>{fullTime(latest)}</time></p>}
      </div>
      {!context && !currentError && <p className="customer-overview-state" role="status">正在读取本话题的往来概况…</p>}
      {currentError && <p className="customer-overview-error" role="alert">{currentError}</p>}
      {context && !context.configured && <p className="customer-overview-state">模型暂不可用，已保存的概况仍可查看。</p>}
      {project?.state === "running" && <p className="customer-overview-state" role="status">正在综合最新往来…</p>}
      {project?.stale && <p className="customer-overview-stale" role="status">有新内容，以下仍为上一次成功概况。</p>}
      {project?.state === "failed" && <p className="customer-overview-error" role="alert">{project.error || "概况更新失败，可稍后重试。"}</p>}
      {summary && <div className="customer-overview-findings">
        {summary.findings.length === 0 && <p className="customer-overview-state">往来中未提供明确的需求信息。</p>}
        {summary.findings.map((finding, index) => <div className="customer-overview-finding" key={`${finding.source_id}:${index}`}>
          {finding.unverified.length > 0 && <p role="alert" className="customer-overview-error">数字待核对：{finding.unverified.join("、")}</p>}
          <p data-suspect={finding.unverified.length > 0 || undefined}>{finding.text}</p>
        </div>)}
      </div>}
      {project?.state === "none" && !summary && <p className="customer-overview-state">还没有本话题的统一概况。</p>}
      {context && !project && <p className="customer-overview-state">当前话题暂无可汇总的往来。</p>}
      {summary && <footer className="customer-overview-footer">
        {(summary.scope.truncated > 0 || summary.scope.unread_attachments > 0) && <p className="customer-overview-stale">覆盖 {summary.scope.included}/{summary.scope.total} 封；{summary.scope.truncated} 封内容截断，{summary.scope.unread_attachments} 份附件未读出。</p>}
        <p>{summary.model}<span aria-hidden> · </span>{summary.task_version}</p>
        <p>更新于 <time dateTime={summary.produced_at}>{fullTime(summary.produced_at)}</time></p>
        <p>按最新往来统一总结 · AI 信息待核对</p>
      </footer>}
    </section>
  </div>;
}
