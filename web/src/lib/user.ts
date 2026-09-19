/** 谁在用。存在这台浏览器里;服务端只认请求头里带的名字(经 tailscale serve 时用它给的登录名)。 */

const KEY = "mail2leads.user";

export function getUser(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setUser(name: string): void {
  try {
    localStorage.setItem(KEY, name.trim());
  } catch {
    /* 私密窗口写不进去,本次会话仍可用 */
  }
}
