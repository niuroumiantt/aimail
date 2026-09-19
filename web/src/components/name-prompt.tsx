import { useState } from "react";
import { Button } from "./button";

/** 先写名字,再做会留下署名的事(确认线索、发信)。名字只存在这台浏览器里;服务端认的是请求头。 */
export function NamePrompt({
  why,
  user,
  onSetUser,
}: {
  why: string;
  user: string;
  onSetUser: (name: string) => void;
}) {
  const [draft, setDraft] = useState(user);
  return (
    <form
      role="group"
      aria-label="你的名字"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-line bg-brand-wash px-4 py-3 text-sm text-brand-deep"
      onSubmit={(e) => {
        e.preventDefault();
        onSetUser(draft);
      }}
    >
      <span>{why}</span>
      <input
        id="user-name"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="例如 Larry"
        className="h-8 rounded-md border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-3"
      />
      <Button type="submit" variant="solid" size="sm" disabled={!draft.trim()}>
        记住
      </Button>
    </form>
  );
}
