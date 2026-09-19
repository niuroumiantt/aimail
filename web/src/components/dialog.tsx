import { Dialog as RadixDialog } from "radix-ui";
import type { ReactNode } from "react";
import { Button } from "./button";

/** 确认对话框。焦点圈定、Esc 关闭、遮罩点击关闭——行为来自 Radix。 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "确认",
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-overlay" />
        <RadixDialog.Content className="fixed left-1/2 top-1/2 z-50 grid w-full max-w-md -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border border-line bg-surface p-5 shadow-lg">
          <div className="grid gap-1">
            <RadixDialog.Title className="text-base font-semibold text-ink">{title}</RadixDialog.Title>
            <RadixDialog.Description className="text-sm text-ink-2">{description}</RadixDialog.Description>
          </div>
          {children}
          <div className="flex justify-end gap-2">
            <RadixDialog.Close asChild>
              <Button variant="ghost">取消</Button>
            </RadixDialog.Close>
            <Button variant="solid" onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
