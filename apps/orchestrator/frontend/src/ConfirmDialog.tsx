import { useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"

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
  open, title, body, confirmLabel = "Borrar", onConfirm, onCancel,
}: {
  open: boolean
  title: string
  body?: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onCancel={e => { e.preventDefault(); onCancel() }}
      className="max-w-sm rounded-lg border border-border bg-background p-0
                 text-foreground backdrop:bg-black/40"
    >
      <div className="space-y-3 p-4">
        <p className="text-sm font-semibold">{title}</p>
        {body && <p className="text-sm text-muted-foreground">{body}</p>}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onCancel}>Cancelar</Button>
          <Button size="sm" variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  )
}
