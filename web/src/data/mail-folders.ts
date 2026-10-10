import { useCallback, useEffect, useRef, useState } from "react";
import { useData } from "./provider";
import type { FolderCommand, MailFolder, MailFolders } from "./types";

const EMPTY: MailFolders = { items: [], assignments: {} };

export function folderPath(items: MailFolder[], id: string): string {
  const path: string[] = [], seen = new Set<string>();
  let item = items.find(f => f.id === id);
  while (item && !seen.has(item.id)) {
    path.unshift(item.name); seen.add(item.id); item = items.find(f => f.id === item?.parent_id);
  }
  return path.join(" / ");
}

export function useMailFolders() {
  const { mailbox, user, mailFolders } = useData();
  const scope = `${mailbox.address}:${user}`;
  const current = useRef(mailFolders);
  const version = useRef(0);
  const [state, setState] = useState<{ scope: string; data: MailFolders; error: string; busy: boolean }>({ scope: "", data: EMPTY, error: "", busy: false });
  useEffect(() => {
    current.current = mailFolders;
    const request = ++version.current;
    let alive = true;
    if (mailbox.address && user) {
      mailFolders().then(data => {
        if (alive && request === version.current) setState({ scope, data, error: "", busy: false });
      }).catch(e => {
        if (alive && request === version.current) setState({ scope, data: EMPTY, error: String(e.message ?? e), busy: false });
      });
    }
    return () => { alive = false; };
  }, [mailFolders, mailbox.address, user, scope]);
  const command = useCallback(async (input?: FolderCommand) => {
    const request = ++version.current;
    setState(s => ({ scope, data: s.scope === scope ? s.data : EMPTY, error: "", busy: true }));
    try {
      const data = await mailFolders(input);
      if (current.current === mailFolders && request === version.current) setState({ scope, data, error: "", busy: false });
      return "";
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      if (current.current === mailFolders && request === version.current) setState(s => ({ ...s, scope, error, busy: false }));
      return error;
    }
  }, [mailFolders, scope]);
  return { ...(state.scope === scope ? state : { data: EMPTY, busy: false, error: "" }), command, enabled: Boolean(user && mailbox.address) };
}

export type FolderController = ReturnType<typeof useMailFolders>;
