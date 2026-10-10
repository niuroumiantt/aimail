/** Only Aimail conversations from this login and mailbox can be filed by dropping. */
export const MAIL_DRAG_TYPE = "application/x-aimail-conversation";

export function startMailDrag(data: DataTransfer, scope: string, threadId: string) {
  // Do not expose the NavLink URL as text/uri-list: Chrome treats it as a page to open.
  data.clearData();
  data.effectAllowed = "move";
  data.setData(MAIL_DRAG_TYPE, JSON.stringify({ version: 1, scope, threadId }));
}

export function draggedThread(data: DataTransfer, scope: string): string | undefined {
  const raw = data.getData(MAIL_DRAG_TYPE);
  if (!raw || raw.length > 2048) return;
  try {
    const value = JSON.parse(raw);
    if (value?.version === 1 && value.scope === scope && typeof value.threadId === "string" && value.threadId.trim() && value.threadId.length <= 100) return value.threadId;
  } catch { /* External links and malformed drags are not mail moves. */ }
}

export function isMailDrag(data: DataTransfer): boolean {
  return Array.from(data.types).includes(MAIL_DRAG_TYPE);
}
