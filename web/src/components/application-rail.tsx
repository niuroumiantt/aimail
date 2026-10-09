import { Inbox, ListTodo, Palette, Users } from "lucide-react";
import { Link, useLocation } from "react-router";
import { ThemeToggle } from "./theme-toggle";

export function ApplicationRail({ leads = false }: { leads?: boolean }) {
  const { pathname } = useLocation();
  const items = [
    { to: "/", name: "邮件", icon: Inbox, active: pathname === "/" || pathname.startsWith("/t/") },
    { to: "/followups", name: "我的跟进", icon: ListTodo, active: pathname.startsWith("/followups") },
    ...(leads ? [{ to: "/leads", name: "销售线索", icon: Users, active: pathname === "/leads" }] : []),
    { to: "/kit", name: "设计组件", icon: Palette, active: pathname === "/kit" },
  ];
  return <nav className="mail-application-rail" aria-label="应用导航">
    <div>{items.map(item => <Link key={item.to} to={item.to} title={item.name} aria-label={item.name} aria-current={item.active ? "page" : undefined}><item.icon size={20} /></Link>)}</div>
    <ThemeToggle />
  </nav>;
}
