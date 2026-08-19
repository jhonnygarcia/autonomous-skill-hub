import { useEffect, useId, useRef } from "react"
import { Button } from "@/components/ui/button"
import { t } from "@/strings"

/**
 * Confirmation on top of the native `<dialog>`.
 *
 * shadcn's `alert-dialog` is not installed on purpose: `showModal()` already gives a
 * focus trap, Escape to close, `::backdrop` and `inert` on the rest of the page — all
 * of which Radix reimplements for browsers this app never runs in. It's a local Vite
 * app; the platform feature is the correct answer here, not the shortcut.
 *
 * React state is the single source of truth: the dialog's own `cancel` event (Escape)
 * is prevented and routed back through `onCancel`, so the element never closes behind
 * the state's back.
 */
export function ConfirmDialog({
  open, title, body, confirmLabel = t("common.delete"), onConfirm, onCancel,
}: {
  open: boolean
  title: string
  body?: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  // Unique per instance — three of these can exist in the tree at once (delete
  // project, delete ticket, discard unsaved form) — so a plain literal id would
  // collide and `aria-labelledby`/`aria-describedby` would point at the wrong dialog.
  const titleId = useId()
  const bodyId = useId()

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  // `m-auto` below restores the centring `showModal()` gets from the UA stylesheet
  // (`inset:0; margin:auto`), which Tailwind's preflight zeroes out — without it the
  // modal pins itself to the top-left corner.
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={body ? bodyId : undefined}
      onCancel={e => { e.preventDefault(); onCancel() }}
      className="m-auto max-w-sm rounded-lg border border-border bg-background p-0
                 text-foreground backdrop:bg-black/40"
    >
      <div className="space-y-3 p-4">
        <p id={titleId} className="text-sm font-semibold">{title}</p>
        {body && <p id={bodyId} className="text-sm text-muted-foreground">{body}</p>}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onCancel}>{t("common.cancel")}</Button>
          <Button size="sm" variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  )
}
