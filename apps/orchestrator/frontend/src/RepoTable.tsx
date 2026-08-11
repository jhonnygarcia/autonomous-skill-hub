import type { Repo } from "@/api"

/**
 * The repo table that used to live inside `ProjectHeader`.
 *
 * It gets extracted because the project list needs the same one: today that
 * information travels in a `title=` attribute, which only appears on hover and is
 * therefore undiscoverable — the third rule of the spec.
 */
export function RepoTable({ repos }: { repos: Repo[] }) {
  // primary first: that's where the agent runs and where it writes
  const sorted = [...repos].sort((a, b) => Number(b.primary) - Number(a.primary))
  return (
    <table className="text-xs">
      <tbody>
        {sorted.map(r => (
          <tr key={r.path}>
            <td className="pr-3 align-top text-muted-foreground">
              {r.label || "sin descripción"}
              {r.primary && <span className="ml-1 text-muted-foreground/70">· principal</span>}
            </td>
            <td className="font-mono text-foreground">{r.path}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
