/** 拼类名。假值被丢掉,免得写一堆三元。 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
