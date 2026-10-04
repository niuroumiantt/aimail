import { CircleUserRound, FileText, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { CustomerContext, Thread } from "@/data/types";
import { fullTime } from "@/lib/text";
import { ReadingCard } from "./reading-card";

export function CustomerWorkspace({ thread, mailbox, revision, load, refresh, onAnalyze }: {
  thread: Thread; mailbox: string; revision: string;
  load: (id: string) => Promise<CustomerContext>;
  refresh: (id: string, retry?: boolean) => Promise<{ queued: number }>;
  onAnalyze: () => Promise<string>;
}) {
  const scope = `${mailbox}:${thread.email}`;
  const [result, setResult] = useState<{ scope: string; value: CustomerContext }>();
  const [error, setError] = useState<{ scope: string; text: string }>();
  const [retry, setRetry] = useState(0);
  const previousRetry = useRef(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const context = result?.scope === scope ? result.value : undefined;
  useEffect(() => {
    const explicitRetry = retry !== previousRetry.current;
    previousRetry.current = retry;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const publish = (value: CustomerContext) => { if (alive) { setResult({ scope, value }); setError(undefined); } };
    const poll = async () => {
      try {
        const value = await load(thread.id);
        if (!alive) return;
        publish(value);
        if (value.projects.some(project => project.state === "running") && Date.now() - started < 600_000) timer = setTimeout(() => void poll(), 2000);
      } catch (e) { if (alive) setError({ scope, text: e instanceof Error ? e.message : String(e) }); }
    };
    void (async () => {
      try {
        const value = await load(thread.id);
        if (!alive) return;
        publish(value);
        if (value.configured && (explicitRetry || value.projects.some(project => project.state === "none" || project.stale && project.state !== "failed"))) {
          await refresh(thread.id, explicitRetry);
        }
        if (alive) await poll();
      } catch (e) { if (alive) setError({ scope, text: e instanceof Error ? e.message : String(e) }); }
    })();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [scope, thread.id, revision, load, refresh, retry]);

  return <div className="customer-workspace-content">
    <section className="customer-profile" aria-label="客户信息">
      <div><CircleUserRound strokeWidth={1.75} /><h2>{thread.contact}</h2></div>
      <p>{thread.email}</p>{thread.region && <p>{thread.region}</p>}
      <small>当前邮箱内同一联系人的来信及我方回复</small>
    </section>
    <section className="customer-summary" aria-label="累计需求摘要">
      <header><Sparkles strokeWidth={1.75} /><h3>累计需求摘要</h3><button type="button" title="重试失败的摘要；已完成且无变化的摘要直接复用" aria-label="更新客户需求摘要" onClick={() => setRetry(value => value + 1)}><RefreshCw size={15} strokeWidth={1.75} /></button></header>
      {!context && !error && <p role="status">正在读取客户往来…</p>}
      {error?.scope === scope && <p role="alert" className="customer-error">{error.text}</p>}
      {context && !context.configured && <p>AI 尚未配置，可继续查看原文和单封读数。</p>}
      {context?.projects.map(project => <article className="customer-project" key={project.id} aria-label={project.subject}>
        <Link className="customer-project-title" to={`/t/${project.id}`}>{project.subject}</Link>
        <small>{project.scope.total} 封往来 · 独立话题</small>
        {project.state === "running" && <p role="status">正在更新需求…</p>}
        {project.stale && <p className="customer-stale" role="status">有新内容，以下仍为上一次成功摘要。</p>}
        {project.state === "failed" && <p className="customer-error" role="alert">{project.error}</p>}
        {project.summary?.model && project.summary.task_version && project.summary.produced_at && <>
          {project.summary.findings.length === 0 && <p>原文未提供可核对的需求信息。</p>}
          {project.summary.findings.map((finding, index) => <div className="customer-finding" key={`${finding.source_id}:${index}`}>
            {finding.unverified.length > 0 && <p role="alert" className="customer-error">这些数字未通过核对：{finding.unverified.join("、")}，请以原文为准。</p>}
            <p data-suspect={finding.unverified.length > 0 || undefined}>{finding.text}</p>
            <Link to={`/t/${project.id}#mail-${finding.source_id}`} title={finding.quote}><FileText size={13} strokeWidth={1.75} />查看原文来源</Link>
          </div>)}
          <p className="customer-attribution" title={project.summary.task_version}>{project.summary.model}<br />{fullTime(project.summary.produced_at)} · {project.summary.task_version}</p>
          {(project.summary.scope.truncated > 0 || project.summary.scope.unread_attachments > 0) && <p className="customer-stale">覆盖 {project.summary.scope.included}/{project.summary.scope.total} 封；{project.summary.scope.truncated} 封内容截断，{project.summary.scope.unread_attachments} 份附件未读出。请核对原文。</p>}
        </>}
        {project.state === "none" && <p>还没有累计摘要。</p>}
        <details className="customer-timeline"><summary>往来与变化来源</summary>{project.messages.map(message => <Link key={message.id} to={`/t/${project.id}#mail-${message.id}`}><span>{message.direction === "out" ? "我方回复" : "对方来信"} · {fullTime(message.sent_at)}</span><span>{message.subject}</span></Link>)}</details>
      </article>)}
      {context?.projects.length === 0 && <p>没有可汇总的往来话题。</p>}
      <small>AI 信息待核对；阅读旧信不会回退累计需求。</small>
    </section>
    <details className="customer-single-reading"><summary>当前邮件的单封读数</summary><ReadingCard reading={thread.reading} analyzing={analyzing} error={analysisError} onAnalyze={!thread.deleted_at ? async () => { setAnalyzing(true); setAnalysisError(""); try { setAnalysisError(await onAnalyze()); } finally { setAnalyzing(false); } } : undefined} /></details>
  </div>;
}
