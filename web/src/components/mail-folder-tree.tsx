import { ChevronDown, ChevronRight, Folder, FolderInput, MoreHorizontal, Plus } from "lucide-react";
import { Dialog, DropdownMenu } from "radix-ui";
import { useRef, useState, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { folderPath, type FolderController } from "@/data/mail-folders";
import type { MailFolder } from "@/data/types";
import { draggedThread, isMailDrag } from "@/lib/mail-drag";
import "@/tokens/mail-folders.css";

type Editor = { action: "create" | "rename" | "delete"; item?: MailFolder };

export function MailFolderTree({ controller, dragScope }: { controller: FolderController; dragScope?: string }) {
  const { data, busy, error, command, enabled } = controller;
  const [params] = useSearchParams();
  const selected = params.get("cf");
  const [closed, setClosed] = useState<string[]>([]);
  const [editor, setEditor] = useState<Editor>();
  const [name, setName] = useState("");
  const [dropTarget, setDropTarget] = useState<string>();
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const moving = useRef(false);
  const dragOver = (event: DragEvent, item: MailFolder) => {
    if (!dragScope || !enabled || busy || moving.current || !isMailDrag(event.dataTransfer)) return;
    event.preventDefault(); event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDropTarget(item.id);
  };
  const drop = async (event: DragEvent, item: MailFolder) => {
    event.preventDefault(); event.stopPropagation(); setDropTarget(undefined);
    if (!dragScope || !enabled || busy || moving.current) return;
    const threadId = draggedThread(event.dataTransfer, dragScope);
    if (!threadId) return;
    const path = folderPath(data.items, item.id);
    if (data.assignments[threadId] === item.id) { setNotice({ text: `这条会话已在“${path}”` }); return; }
    moving.current = true; setNotice({ text: `正在移至“${path}”…` });
    try {
      const problem = await command({ action: "move", thread_id: threadId, folder_id: item.id });
      setNotice(problem ? { text: problem, error: true } : { text: `已移至“${path}”` });
    } finally { moving.current = false; }
  };
  const open = (value: Editor) => { setEditor(value); setName(value.action === "rename" ? value.item!.name : ""); };
  const save = async () => {
    if (!editor || busy) return;
    const problem = await command(editor.action === "create" ? { action: "create", name: name.trim(), parent_id: editor.item?.id ?? null }
      : editor.action === "rename" ? { action: "rename", id: editor.item!.id, name: name.trim() }
      : { action: "delete", id: editor.item!.id });
    if (!problem) { if (editor.item) setClosed(s => s.filter(id => id !== editor.item!.id)); setEditor(undefined); }
  };
  const branch = (parent: string | null, depth = 1) => <ul>{data.items.filter(f => f.parent_id === parent).map(item => {
    const children = data.items.some(f => f.parent_id === item.id);
    const expanded = !closed.includes(item.id);
    return <li key={item.id}>
      <div className="mail-folder-row" data-selected={selected === item.id} data-drop-target={dropTarget === item.id || undefined} style={{ paddingLeft: (depth - 1) * 12 }}
        onDragEnter={event => dragOver(event, item)} onDragOver={event => dragOver(event, item)}
        onDragLeave={event => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDropTarget(current => current === item.id ? undefined : current); }}
        onDrop={event => void drop(event, item)}>
        {children ? <button type="button" className="mail-folder-caret" aria-label={`${expanded ? "收起" : "展开"}${item.name}`} aria-expanded={expanded} onClick={() => setClosed(s => s.includes(item.id) ? s.filter(id => id !== item.id) : [...s, item.id])}>{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button> : <span className="mail-folder-caret" />}
        <Link draggable={false} to={`/?cf=${encodeURIComponent(item.id)}`} title={folderPath(data.items, item.id)} aria-current={selected === item.id ? "page" : undefined}><Folder size={15} /><span>{item.name}</span><small>{item.count || ""}</small></Link>
        <DropdownMenu.Root><DropdownMenu.Trigger asChild><button className="mail-folder-more" type="button" aria-label={`${item.name}的文件夹操作`}><MoreHorizontal size={15} /></button></DropdownMenu.Trigger>
          <DropdownMenu.Portal><DropdownMenu.Content className="mail-folder-menu" sideOffset={4}>
            <DropdownMenu.Item disabled={depth >= 3 || busy} onSelect={() => open({ action: "create", item })}>{depth >= 3 ? "已到第三层" : "新建子文件夹"}</DropdownMenu.Item>
            <DropdownMenu.Item disabled={busy} onSelect={() => open({ action: "rename", item })}>重命名</DropdownMenu.Item>
            <DropdownMenu.Item disabled={busy} onSelect={() => open({ action: "delete", item })}>删除空文件夹</DropdownMenu.Item>
          </DropdownMenu.Content></DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
      {children && expanded && branch(item.id, depth + 1)}
    </li>;
  })}</ul>;
  return <section className="mail-personal-folders" aria-label="自建文件夹">
    <header><h2>自建文件夹</h2><button type="button" aria-label="新建文件夹" title="新建文件夹（最多三层）" disabled={busy || !enabled} onClick={() => open({ action: "create" })}><Plus size={16} /></button></header>
    {branch(null)}
    {data.items.length > 0 && dragScope && <p className="mail-folder-hint">拖动邮件到文件夹，或点击邮件上方的“移动”</p>}
    {notice && <p role={notice.error ? "alert" : "status"} className={notice.error ? "mail-folder-error" : "mail-folder-notice"}>{notice.text}</p>}
    {!data.items.length && !error && <p className="mail-folder-hint">{enabled ? "点击 + 创建，最多三层" : "登录后可创建个人文件夹"}</p>}
    {error && !editor && error !== notice?.text && <p role="alert" className="mail-folder-error">{error}<button type="button" disabled={busy} onClick={() => void command()}>重试</button></p>}
    <Dialog.Root open={Boolean(editor)} onOpenChange={value => { if (!value && !busy) setEditor(undefined); }}><Dialog.Portal>
      <Dialog.Overlay className="mail-folder-overlay" /><Dialog.Content className="mail-folder-dialog">
        <Dialog.Title>{editor?.action === "delete" ? "删除空文件夹" : editor?.action === "rename" ? "重命名文件夹" : "新建文件夹"}</Dialog.Title>
        <Dialog.Description>{editor?.action === "delete" ? "只删除空文件夹，邮件原件始终保留。" : `位置：${editor?.action === "create" && editor.item ? folderPath(data.items, editor.item.id) : "当前邮箱的个人文件夹"}`}</Dialog.Description>
        <form onSubmit={e => { e.preventDefault(); void save(); }}>
          {editor?.action !== "delete" && <label>文件夹名称<input autoFocus maxLength={80} value={name} disabled={busy} onChange={e => setName(e.target.value)} required /></label>}
          {error && <p role="alert" className="mail-folder-error">{error}</p>}
          <footer><button type="button" disabled={busy} onClick={() => setEditor(undefined)}>取消</button><button type="submit" disabled={busy || (editor?.action !== "delete" && !name.trim())}>{busy ? "保存中…" : editor?.action === "delete" ? "删除" : "保存"}</button></footer>
        </form>
      </Dialog.Content></Dialog.Portal></Dialog.Root>
  </section>;
}

export function MoveToFolder({ controller, threadId }: { controller: FolderController; threadId: string }) {
  const [open, setOpen] = useState(false);
  const [destination, setDestination] = useState("");
  const { data, busy, error, command, enabled } = controller;
  return <Dialog.Root open={open} onOpenChange={value => { if (!busy) { setOpen(value); setDestination(data.assignments[threadId] ?? ""); } }}>
    <Dialog.Trigger asChild><button type="button" disabled={!enabled || busy} title="整理到个人文件夹"><FolderInput size={18} />移动</button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="mail-folder-overlay" /><Dialog.Content className="mail-folder-dialog">
      <Dialog.Title>移动到文件夹</Dialog.Title><Dialog.Description>整理整条邮件会话，保留原文及业务状态。新回复也会保留在这条会话内。</Dialog.Description>
      <form onSubmit={e => { e.preventDefault(); void command({ action: "move", thread_id: threadId, folder_id: destination || null }).then(problem => { if (!problem) setOpen(false); }); }}>
        <label>目标文件夹<select autoFocus value={destination} onChange={e => setDestination(e.target.value)} disabled={busy}>
          <option value="">不放入自建文件夹</option>{data.items.map(f => <option key={f.id} value={f.id}>{folderPath(data.items, f.id)}</option>)}
        </select></label>
        {!data.items.length && <p className="mail-folder-hint">请先在邮箱导航中点击 + 创建文件夹。</p>}
        {error && <p role="alert" className="mail-folder-error">{error}</p>}
        <footer><button type="button" disabled={busy} onClick={() => setOpen(false)}>取消</button><button type="submit" disabled={busy}>{busy ? "保存中…" : "确定"}</button></footer>
      </form>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}
