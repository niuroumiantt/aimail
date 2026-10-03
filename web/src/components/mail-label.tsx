import type { MailType, Reading, Thread } from "@/data/types";
import { Pill } from "./pill";

export const MAIL_LABEL: Record<MailType, string> = {
  inquiry: "客户询价", newsletter: "新闻订阅", promotion: "广告推销",
  billing: "账单财务", notification: "系统通知", business: "业务往来", other: "其他邮件",
};

export function mailType(reading?: Reading): MailType | undefined {
  if (!reading || reading.status !== "ok") return undefined;
  if (reading.is_inquiry) return "inquiry";
  return reading.mail_type && reading.mail_type !== "inquiry" ? reading.mail_type : "other";
}

export function isLeadThread(thread: Thread): boolean {
  return Boolean(thread.has_lead || mailType(thread.reading) === "inquiry");
}

export function MailLabel({ thread }: { thread: Thread }) {
  const type = mailType(thread.reading);
  const lead = isLeadThread(thread);
  const label = thread.has_lead ? "客户线索" : lead ? "潜在线索" : type ? MAIL_LABEL[type] : "待识别";
  return <Pill tone={lead ? "brand" : "neutral"} dot={lead}>{label}</Pill>;
}
