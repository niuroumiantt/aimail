/** Design-only local server log. No claim of authenticated employee identity. */
export async function recordDesignAudit(action: string, detail: unknown): Promise<void> {
  const response = await fetch("/__design/audit", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, detail, client_time: new Date().toISOString() }),
  });
  if (!response.ok) throw new Error("操作记录未能写入服务端，请稍后重试");
  const receipt = await response.json();
  if (receipt.recorded !== true) throw new Error("服务端未确认记录");
}
