/** 人名 → 头像缩写。中日韩名取第一个字;拉丁名取前两个词的首字母。 */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  if (/^[㐀-鿿가-힯]/.test(trimmed)) return trimmed[0];
  return trimmed
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/** 稳定的哈希,用来给同一个人固定一个头像色。 */
export function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h);
}

const rtf = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });

/** 列表里用的相对时间:刚刚 / 3 小时前 / 昨天 / 9月12日 */
export function relativeTime(iso: string, now = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.round((then.getTime() - now.getTime()) / 60000);
  if (Math.abs(minutes) < 1) return "刚刚";
  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 7) return rtf.format(days, "day");
  return then.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function fullTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 回信主题:已经是 Re: / 回复: 的不再叠一层 */
export function replySubject(subject: string): string {
  return /^\s*(re|回复|答复)\s*[:：]/i.test(subject) ? subject.trim() : `Re: ${subject.trim()}`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
}
