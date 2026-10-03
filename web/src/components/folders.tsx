import type { Folder, Thread } from "@/data/types";
import { isLeadThread } from "./mail-label";
import type { Tone } from "./pill";

export type FolderKey = Folder | "all" | "leads" | "trash";

export const FOLDER_LABEL: Record<FolderKey, string> = {
  all: "全部",
  inbox: "待跟进",
  quote: "待报价",
  replied: "已回复",
  invalid: "其他邮件",
  leads: "线索邮件",
  trash: "回收站",
};

export const FOLDER_TONE: Record<Folder, Tone> = {
  inbox: "brand",
  quote: "warn",
  replied: "ok",
  invalid: "neutral",
};

export const FOLDER_ORDER: FolderKey[] = ["all", "leads", "inbox", "quote", "replied", "invalid", "trash"];

export function inFolder(thread: Thread, folder: FolderKey): boolean {
  if (folder === "trash") return Boolean(thread.deleted_at);
  if (thread.deleted_at) return false;
  if (folder === "all") return true;
  if (folder === "leads") return isLeadThread(thread);
  if (folder === "invalid") return !isLeadThread(thread);
  if (folder === "inbox") return isLeadThread(thread) && ["inbox", "invalid"].includes(thread.folder);
  return thread.folder === folder;
}

export function countFolders(threads: Thread[]): Record<FolderKey, number> {
  const counts: Record<FolderKey, number> = { all: 0, leads: 0, inbox: 0, quote: 0, replied: 0, invalid: 0, trash: 0 };
  for (const thread of threads) for (const key of FOLDER_ORDER) if (inFolder(thread, key)) counts[key]++;
  return counts;
}
