import { Check, ChevronDown, Cpu, RefreshCw, Terminal } from "lucide-react";
import { Popover } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import type { ModelProvider, ModelSelection } from "@/data/types";

export function ModelSelector({ mailbox, load, save }: {
  mailbox: string;
  load: () => Promise<ModelSelection>;
  save: (selected: ModelProvider) => Promise<ModelSelection>;
}) {
  const [result, setResult] = useState<{ scope: string; value: ModelSelection }>();
  const [error, setError] = useState<{ scope: string; text: string }>();
  const [busy, setBusy] = useState<{ scope: string; request: number }>();
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(false);
  const active = useRef<{ alive: boolean; request: number } | undefined>(undefined);
  const selection = result?.scope === mailbox ? result.value : undefined;
  const currentError = error?.scope === mailbox ? error.text : undefined;
  const saving = busy?.scope === mailbox;
  const selected = selection?.options.find(option => option.id === selection.selected);
  const label = selected?.label ?? (selection ? `${selection.model || selection.selected} · 服务默认` : "尚未加载");
  useEffect(() => {
    const scope = { alive: true, request: 1 };
    active.current = scope;
    const request = scope.request;
    void load().then(value => {
      if (scope.alive && request === scope.request) { setResult({ scope: mailbox, value }); setError(undefined); setBusy(undefined); }
    }).catch(reason => {
      if (scope.alive && request === scope.request) { setError({ scope: mailbox, text: reason instanceof Error ? reason.message : String(reason) }); setBusy(undefined); }
    });
    return () => { scope.alive = false; };
  }, [mailbox, load, retry]);
  const choose = async (provider: ModelProvider) => {
    if (!selection || saving || provider === selection.selected) return;
    const option = selection.options.find(item => item.id === provider);
    if (!option?.available) return;
    const scope = active.current;
    if (!scope?.alive) return;
    const request = ++scope.request;
    setBusy({ scope: mailbox, request });
    setError(undefined);
    try {
      const value = await save(provider);
      if (scope.alive && request === scope.request) {
        if (value.selected !== provider) throw new Error("服务端没有保存所选模型，请重试。");
        setResult({ scope: mailbox, value });
      }
    } catch (reason) {
      if (scope.alive && request === scope.request) setError({ scope: mailbox, text: reason instanceof Error ? reason.message : String(reason) });
    } finally {
      if (scope.alive && request === scope.request) setBusy(undefined);
    }
  };
  return <div className="mail-model-selector">
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild><button type="button" className="mail-model-trigger" aria-label={`选择邮件识别模型：${label}`} title={selection ? `${label} · ${selection.model || "未连接"}。用于新分析；已有摘要保留。` : "读取当前邮箱的模型设置"}>
        <Cpu size={16} /><span>{saving ? "正在保存…" : selection ? label : currentError ? "模型未加载" : "读取模型…"}</span><ChevronDown size={14} />
      </button></Popover.Trigger>
      <Popover.Portal><Popover.Content className="mail-model-menu" align="start" sideOffset={8} collisionPadding={16} aria-label="邮件识别模型">
        <header><div><h2>邮件识别模型</h2><small>用于新分析；已有摘要保留</small></div><button className="mail-icon-button" type="button" aria-label="刷新模型连接状态" title="只读取连接状态，不重新分析邮件" disabled={saving} onClick={() => setRetry(value => value + 1)}><RefreshCw size={16} /></button></header>
        {!selection && !currentError && <p role="status">正在读取可用模型…</p>}
        {selection && !selected && <p>当前服务默认：{selection.model || selection.selected}。下列连接用于后续新分析。</p>}
        {selection?.options.map(option => <button key={option.id} className="mail-model-option" type="button" disabled={!option.available || saving} aria-pressed={option.id === selection.selected} onClick={() => void choose(option.id)}>
          {option.id === "local" ? <Cpu size={16} /> : <Terminal size={16} />}
          <span><strong>{option.label}</strong><small>{!option.available ? `未连接 · ${option.reason}` : option.model || option.reason || "可用于新分析"}</small>{option.available && option.model && option.reason && <small>{option.reason}</small>}</span>
          {option.id === selection.selected && <Check size={16} />}
        </button>)}
        {saving && <p role="status">正在保存当前邮箱的模型设置…</p>}
        {currentError && <div className="mail-model-error"><p role="alert">{currentError}</p>{!selection && <button type="button" onClick={() => setRetry(value => value + 1)}><RefreshCw size={14} />重新读取</button>}</div>}
        <footer>切换不会重读已有邮件。旧摘要旁的模型署名保持原样。</footer>
      </Popover.Content></Popover.Portal>
    </Popover.Root>
  </div>;
}
