import { useEffect, useState } from "react";
import { ChevronDown, CircleUserRound } from "lucide-react";

type Session = { identity: string; username: string };

const PROFILE_URL = "https://login.glocalstorage.cn/if/user/#/settings";
const SIGN_OUT_URL = "/oauth2/sign_out?rd=https%3A%2F%2Flogin.glocalstorage.cn%2Fif%2Fuser%2F";

export function AccountMenu() {
  const [session, setSession] = useState<Session>();
  useEffect(() => {
    let active = true;
    fetch("/api/session", { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(response => response.ok ? response.json() as Promise<Session> : undefined)
      .then(value => { if (active && value && typeof value.identity === "string") setSession({ identity: value.identity, username: typeof value.username === "string" ? value.username : "" }); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  return (
    <header className="flex h-10 shrink-0 items-center justify-end border-b border-line bg-surface px-4 text-xs">
      <details className="group relative">
        <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md px-2 py-1.5 text-ink-2 hover:bg-surface-2">
          <span className="mail-account-icon" aria-hidden><CircleUserRound size={18} strokeWidth={1.75} /></span>
          <span className="mail-account-name max-w-56 truncate">{session ? session.username.trim() || session.identity.split("@")[0] : "正在读取账号…"}</span>
          <ChevronDown size={13} aria-hidden />
        </summary>
        <div className="absolute right-0 z-50 mt-1 grid min-w-52 gap-1 rounded-lg border border-line bg-surface p-2 shadow-lg">
          <p className="break-all px-2 py-1 text-2xs text-ink-3">当前登录：{session?.identity ?? "未知"}</p>
          <a className="rounded px-2 py-2 text-ink hover:bg-surface-2" href={PROFILE_URL}>个人资料与账号设置</a>
          <a className="rounded px-2 py-2 text-danger hover:bg-surface-2" href={SIGN_OUT_URL}>退出当前应用</a>
        </div>
      </details>
    </header>
  );
}
