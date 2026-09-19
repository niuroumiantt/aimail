import { Tooltip } from "radix-ui";
import type { ReactNode } from "react";

/** 提示。键盘可达、延迟 300ms、位置自动翻转——这些行为来自 Radix,不自己写。 */
export function Tip({
  label,
  side = "bottom",
  children,
}: {
  label: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactNode;
}) {
  return (
    <Tooltip.Root delayDuration={300}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="z-50 select-none rounded-md bg-ink px-2 py-1 text-xs text-canvas shadow-md"
        >
          {label}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const TipProvider = Tooltip.Provider;
