import type { MailType, Reading, Thread } from "@/data/types";
import { Pill } from "./pill";
import { Zap } from "lucide-react";

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
  return Boolean(thread.has_lead || thread.has_trade || ["inquiry", "business"].includes(mailType(thread.reading) ?? ""));
}

export function MailLabel({ thread }: { thread: Thread }) {
  const type = mailType(thread.reading);
  const lead = isLeadThread(thread);
  if (lead) return <span className="mail-sales-lead" title={thread.has_lead ? "已确认客户线索" : "买卖相关往来，业务信息需核对"}><Zap size={12} strokeWidth={1.75} />SALES LEAD</span>;
  return <Pill tone="neutral">{type ? MAIL_LABEL[type] : "待识别"}</Pill>;
}
