import { useId, type ReactNode } from "react"

/**
 * An explanation behind a visible `[i]`, in the browser's top layer.
 *
 * NOT a `title=` tooltip. This repo already ruled that information visible only on
 * hover is information nobody finds (see `RepoTable`) — but that rule is about the
 * *affordance*, not the text. Here the button is always on screen and says there's
 * something to read; only the reading is deferred. Click and not hover, so it works
 * the same with a finger and with a keyboard, and doesn't flicker while you scan a
 * column of them.
 *
 * Native `popover`, so there is no open/close state to hold: light dismiss, Escape and
 * focus return come from the platform, and the top layer is why the popup can't be
 * clipped by the `overflow-x-auto` its table lives in — which is exactly what would
 * happen to an absolutely positioned div.
 */
export function Info({ label, children }: { label: string; children: ReactNode }) {
  // `useId` yields `«r0»`-style values; strip everything an HTML id shouldn't carry.
  const id = `info-${useId().replace(/[^a-zA-Z0-9]/g, "")}`
  return (
    <>
      <button type="button" popoverTarget={id} aria-label={`Explicación: ${label}`}
              className="ml-1 align-middle text-xs text-muted-foreground
                         hover:text-foreground focus-visible:outline-1
                         focus-visible:outline-ring">
        [i]
      </button>
      {/* `m-auto` for the same reason `ConfirmDialog` needs it: the UA centres an open
          popover with `inset:0; margin:auto`, and Tailwind's preflight zeroes margins. */}
      <div id={id} popover="auto"
           className="m-auto max-w-md space-y-2 rounded-sm border border-border
                      bg-background p-4 text-left text-xs font-normal normal-case
                      tracking-normal text-muted-foreground backdrop:bg-black/30">
        <p className="text-sm font-bold text-foreground">{label}</p>
        {children}
      </div>
    </>
  )
}
