import type { ReactNode } from "react"

/**
 * A minimal markdown → React renderer, built for exactly what the ticket-agent skills
 * write (see `plugins/ticket-agent/skills/*\/SKILL.md`'s templates and a real
 * `docs/tickets/<id>-analysis.md`): headings, paragraphs, bold/italic/inline code,
 * fenced code blocks, lists (ordered, unordered, task checkboxes), tables, blockquotes,
 * links, horizontal rules.
 *
 * **No `dangerouslySetInnerHTML`, on purpose.** The text comes from an AI agent quoting
 * the target repo's own code and comments — building an HTML string out of that and
 * injecting it would be exactly the injection surface this file exists to avoid.
 * Every node below is a React element built from parsed fragments, never from a
 * string of markup, so there is no HTML for the browser to parse as anything but text.
 *
 * **Nothing recognized degrades to nothing.** Every input line lands in SOME block —
 * the fallback is a paragraph, not a skip — and inline syntax that doesn't match a
 * known pattern is left as the literal characters it was. A skill that reaches for
 * markdown this renderer doesn't cover (an image, a footnote) still reads as text,
 * never disappears.
 */

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "hr" }
  | { type: "code"; lang: string; code: string }
  | { type: "blockquote"; text: string }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "list"; ordered: boolean; items: { text: string; checked: boolean | null }[] }
  | { type: "paragraph"; text: string }

const FENCE_RE = /^```\s*(\S*)\s*$/
const HEADING_RE = /^(#{1,6})\s+(.*)$/
const HR_RE = /^(-{3,}|\*{3,}|_{3,})\s*$/
const QUOTE_RE = /^ {0,3}>\s?/
const LIST_RE = /^(\s*)([-*+]|\d+\.)\s+(.*)$/
const TASK_RE = /^\[( |x|X)\]\s+(.*)$/
// The whole line is dashes/colons/pipes/spaces — markdown's table separator row
// (`|---|---|`, `---|---`, with or without `:` alignment markers).
const TABLE_SEP_RE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

function isOrdered(marker: string): boolean {
  return /^\d+\.$/.test(marker)
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim())
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n")
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === "") { i++; continue }

    const fence = line.match(FENCE_RE)
    if (fence) {
      const lang = fence[1] || ""
      const codeLines: string[] = []
      i++
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { codeLines.push(lines[i]); i++ }
      i++   // the closing fence, or just past the end if the block was never closed
      blocks.push({ type: "code", lang, code: codeLines.join("\n") })
      continue
    }

    const heading = line.match(HEADING_RE)
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() })
      i++
      continue
    }

    if (HR_RE.test(line.trim())) {
      blocks.push({ type: "hr" })
      i++
      continue
    }

    if (QUOTE_RE.test(line)) {
      const qLines: string[] = []
      while (i < lines.length && QUOTE_RE.test(lines[i])) {
        qLines.push(lines[i].replace(QUOTE_RE, ""))
        i++
      }
      blocks.push({ type: "blockquote", text: qLines.join(" ") })
      continue
    }

    // A table needs the header row's OWN line to carry a pipe (so a plain sentence
    // that happens to be followed, coincidentally, by a run of dashes never qualifies)
    // and the line right after it to be nothing but a separator row.
    if (line.includes("|") && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(splitRow(lines[i]))
        i++
      }
      blocks.push({ type: "table", header, rows })
      continue
    }

    const listStart = line.match(LIST_RE)
    if (listStart) {
      const ordered = isOrdered(listStart[2])
      const items: { text: string; checked: boolean | null }[] = []
      while (i < lines.length) {
        const m = lines[i].match(LIST_RE)
        if (!m || isOrdered(m[2]) !== ordered) break
        let content = m[3]
        i++
        // Lazy continuation: indented prose right under an item, exactly how the
        // skills write a `DECIDIR`/`BLOQUEA` item's body under its checkbox line.
        while (i < lines.length && lines[i].trim() !== "" && !LIST_RE.test(lines[i])) {
          content += " " + lines[i].trim()
          i++
        }
        const task = content.match(TASK_RE)
        items.push(task ? { text: task[2], checked: task[1].toLowerCase() === "x" }
                         : { text: content, checked: null })
      }
      blocks.push({ type: "list", ordered, items })
      continue
    }

    const paraLines: string[] = [line]
    i++
    while (i < lines.length && lines[i].trim() !== "" &&
           !FENCE_RE.test(lines[i]) && !HEADING_RE.test(lines[i]) &&
           !LIST_RE.test(lines[i]) && !QUOTE_RE.test(lines[i]) &&
           !HR_RE.test(lines[i].trim())) {
      paraLines.push(lines[i])
      i++
    }
    blocks.push({ type: "paragraph", text: paraLines.join(" ") })
  }
  return blocks
}

// Code spans first (their content is literal, never re-parsed), then bold — which the
// real analysis nests italic and inline code INSIDE (3359: "**ticket hermano en
// `ProvidenceTMS`, ejecutado *antes* del borrado aquí**") — then italic, then links.
// A single `*` can't win at a position where `**` also matches: `[^*\n]+` demands at
// least one non-`*` character, and the character right after `**`'s first `*` is
// another `*`, so the italic alternative simply fails to match there and the engine
// falls through to bold. A fresh RegExp is built per call (not a shared module-level
// one) because bold/italic/link text recurse into this same function, and a shared
// `lastIndex` would corrupt the caller's position mid-scan.
function parseInline(text: string): ReactNode[] {
  const re = /`([^`\n]+)`|\*\*([\s\S]+?)\*\*|\*([^*\n]+)\*|\[([^\]]+)\]\(([^)\s]+)\)/g
  const out: ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const [, code, bold, italic, linkText, linkHref] = m
    if (code !== undefined) {
      out.push(
        <code key={out.length} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {code}
        </code>
      )
    } else if (bold !== undefined) {
      out.push(<strong key={out.length}>{parseInline(bold)}</strong>)
    } else if (italic !== undefined) {
      out.push(<em key={out.length}>{parseInline(italic)}</em>)
    } else if (linkText !== undefined) {
      out.push(
        <a key={out.length} href={linkHref} target="_blank" rel="noreferrer"
           className="text-primary underline underline-offset-2">
          {parseInline(linkText)}
        </a>
      )
    }
    last = re.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const HEADING_CLASS: Record<number, string> = {
  1: "mt-4 mb-2 text-xl font-bold tracking-tight text-foreground",
  2: "mt-4 mb-2 text-lg font-semibold tracking-tight text-foreground",
  3: "mt-3 mb-1.5 text-base font-semibold text-foreground",
  4: "mt-3 mb-1.5 text-sm font-semibold text-foreground",
  5: "mt-2 mb-1 text-sm font-semibold text-foreground",
  6: "mt-2 mb-1 text-sm font-semibold text-muted-foreground",
}

function Heading({ level, children }: { level: number; children: ReactNode }) {
  const cls = HEADING_CLASS[level] ?? HEADING_CLASS[6]
  switch (Math.min(level, 6)) {
    case 1: return <h1 className={cls}>{children}</h1>
    case 2: return <h2 className={cls}>{children}</h2>
    case 3: return <h3 className={cls}>{children}</h3>
    case 4: return <h4 className={cls}>{children}</h4>
    case 5: return <h5 className={cls}>{children}</h5>
    default: return <h6 className={cls}>{children}</h6>
  }
}

function renderBlock(b: Block, key: number): ReactNode {
  switch (b.type) {
    case "heading":
      return <Heading key={key} level={b.level}>{parseInline(b.text)}</Heading>
    case "hr":
      return <hr key={key} className="my-4 border-border" />
    case "code":
      return (
        <pre key={key} className="my-2 overflow-x-auto rounded-md border border-border bg-muted/50 p-3 text-xs">
          <code className="font-mono">{b.code}</code>
        </pre>
      )
    case "blockquote":
      return (
        <blockquote key={key} className="my-2 border-l-2 border-border pl-3 text-muted-foreground italic">
          {parseInline(b.text)}
        </blockquote>
      )
    case "table":
      return (
        <div key={key} className="my-2 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {b.header.map((c, ci) => (
                  <th key={ci} className="border-b border-border px-2 py-1 text-left font-semibold text-foreground">
                    {parseInline(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci} className="border-b border-border/50 px-2 py-1 align-top">
                      {parseInline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    case "list": {
      const items = b.items.map((it, ii) => (
        <li key={ii} className={it.checked !== null ? "flex list-none items-start gap-1.5 -ml-5" : ""}>
          {it.checked !== null && (
            <input type="checkbox" checked={it.checked} readOnly disabled className="mt-1 shrink-0" />
          )}
          <span>{parseInline(it.text)}</span>
        </li>
      ))
      return b.ordered
        ? <ol key={key} className="my-2 list-decimal space-y-1 pl-5 text-sm">{items}</ol>
        : <ul key={key} className="my-2 list-disc space-y-1 pl-5 text-sm">{items}</ul>
    }
    case "paragraph":
      return <p key={key} className="my-2 leading-relaxed">{parseInline(b.text)}</p>
  }
}

export function Markdown({ text }: { text: string }) {
  return <div className="text-sm text-foreground">{parseBlocks(text).map((b, i) => renderBlock(b, i))}</div>
}
