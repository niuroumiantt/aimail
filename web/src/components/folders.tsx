import type { Folder } from "@/data/types";
import type { Tone } from "./pill";

export type FolderKey = Folder | "all";

export const FOLDER_LABEL: Record<FolderKey, string> = {
  all: "全部",
  inbox: "待处理",
  quote: "待报价",
  replied: "已回复",
  invalid: "无效",
};

export const FOLDER_TONE: Record<Folder, Tone> = {
  inbox: "brand",
  quote: "warn",
  replied: "ok",
  invalid: "neutral",
};

export const FOLDER_ORDER: FolderKey[] = ["all", "inbox", "quote", "replied", "invalid"];
