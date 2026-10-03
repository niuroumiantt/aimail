import { Ban, FileText, Sparkles, TriangleAlert } from "lucide-react";
import type { Reading } from "@/data/types";
import { Tip } from "./tip";
import { MAIL_LABEL, mailType } from "./mail-label";

/** 列表里那一个小图标:读数是什么状态,一眼看到。 */
export function StatusGlyph({ reading }: { reading?: Reading }) {
  if (!reading) return <span className="size-4" aria-hidden />;
  const props = { size: 15, strokeWidth: 2 } as const;
  if (reading.status === "failed")
    return (
      <Tip label="模型没读出来,请看原文">
        <Ban {...props} className="text-danger-text" aria-label="读数失败" />
      </Tip>
    );
  if (!reading.is_inquiry && reading.unverified.length === 0)
    return (
      <Tip label={MAIL_LABEL[mailType(reading) ?? "other"]}>
        <FileText {...props} className="text-ink-2" aria-label="已摘要" />
      </Tip>
    );
  if (reading.unverified.length > 0)
    return (
      <Tip label="摘要里有原文没有的数字">
        <TriangleAlert {...props} className="text-warn-text" aria-label="数字可疑" />
      </Tip>
    );
  return (
    <Tip label="已读出,数字全部核对通过">
      <Sparkles {...props} className="text-brand" aria-label="已读出" />
    </Tip>
  );
}
