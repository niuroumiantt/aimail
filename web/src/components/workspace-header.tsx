import { Inbox, ListChecks, Palette, Send, Users } from "lucide-react";
import { Link, useLocation } from "react-router";
import { ApplicationHeader } from "./app-shell";
import "@/tokens/workspace-layout.css";

const WORKSPACES = [
  { href: "/", label: "收件箱", icon: Inbox },
  { href: "/leads", label: "线索", icon: Users },
  { href: "/followups", label: "我的跟进", icon: ListChecks },
  { href: "/outreach", label: "开发信序列", icon: Send },
  { href: "/kit", label: "组件", icon: Palette },
];

/** Independent workspaces keep the mailbox brand, navigation and account controls. */
export function WorkspaceHeader() {
  const { pathname } = useLocation();
  return <div className="mail-workspace-header"><ApplicationHeader title="工作台" navigation={
    <nav className="mail-workspace-nav" aria-label="主导航">
      {WORKSPACES.map(({ href, label, icon: Icon }) => <Link key={href} to={href}
        aria-current={href === "/" ? pathname === "/" ? "page" : undefined : pathname.startsWith(href) ? "page" : undefined}>
        <Icon size={16} strokeWidth={1.75}/><span>{label}</span>
      </Link>)}
    </nav>
  }/></div>;
}
