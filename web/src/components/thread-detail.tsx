import { ArrowLeft, Archive, Reply, Tag } from "lucide-react";
import { Link } from "react-router";
import type { Thread } from "@/data/types";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { MessageView } from "./message";
import { Pill } from "./pill";
import { ReadingCard } from "./reading-card";
import { Tip } from "./tip";

export function ThreadDetail({ thread, backSearch }: { thread: Thread; backSearch: string }) {
  return (
    <>
      <header className="flex items-start gap-3 border-b border-line bg-surface px-5 py-4">
        <Link
          to={{ pathname: "/", search: backSearch }}
          aria-label="返回列表"
          className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface-2 md:hidden"
        >
          <ArrowLeft size={16} strokeWidth={2} />
        </Link>
        <Avatar name={thread.contact} size="lg" muted={thread.folder === "invalid"} />
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-snug text-ink text-balance">{thread.subject}</h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-2">
            <span className="font-medium text-ink">{thread.contact}</span>
            <span>{thread.company}</span>
            {thread.region && <span className="text-ink-3">·</span>}
            {thread.region && <span>{thread.region}</span>}
            <span className="text-ink-3">·</span>
            <span className="font-mono">{thread.email}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Pill tone={FOLDER_TONE[thread.folder]} dot>
            {FOLDER_LABEL[thread.folder]}
          </Pill>
          <Tip label="回复(M5 起可用)">
            <Button size="sm" icon={<Reply size={14} strokeWidth={2} />} disabled>
              回复
            </Button>
          </Tip>
          <Tip label="改标签">
            <Button size="sm" variant="ghost" aria-label="改标签" icon={<Tag size={15} strokeWidth={1.75} />} />
          </Tip>
          <Tip label="归档">
            <Button size="sm" variant="ghost" aria-label="归档" icon={<Archive size={15} strokeWidth={1.75} />} />
          </Tip>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-3xl gap-5 px-5 py-5">
          <ReadingCard reading={thread.reading} />
          {thread.messages.map((m) => (
            <MessageView key={m.id} message={m} />
          ))}
        </div>
      </div>
    </>
  );
}
