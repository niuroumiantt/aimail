import { useEffect, useState } from "react";
import { LogIn } from "lucide-react";
import { SESSION_EXPIRED_EVENT, signInUrl } from "@/lib/session-auth";

export function SessionNotice() {
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const onExpired = () => setExpired(true);
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);
  if (!expired) return null;
  return <div role="alert" className="mail-session-notice">
    <span>登录已过期，重新登录后即可继续使用。</span>
    <a href={signInUrl()}><LogIn size={16} aria-hidden />重新登录</a>
  </div>;
}
