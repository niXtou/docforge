import type { ReactNode } from 'react'

const TOKEN = /("(?:\\.|[^"\\])*"\s*:?)|(-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g

/** Tokenize a pretty-printed JSON string into colored spans for the editorial palette. */
export function highlightJson(input: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let i = 0
  let m: RegExpExecArray | null
  TOKEN.lastIndex = 0

  while ((m = TOKEN.exec(input))) {
    if (m.index > last) out.push(input.slice(last, m.index))
    if (m[1]) {
      const isKey = m[1].trimEnd().endsWith(':')
      if (isKey) {
        const colon = m[1].lastIndexOf(':')
        out.push(
          <span key={`k${i}`} className="text-[var(--color-ember-400)]">
            {m[1].slice(0, colon)}
          </span>,
          <span key={`p${i}`} className="text-[var(--color-ink-tertiary)]">
            {m[1].slice(colon)}
          </span>,
        )
      } else {
        out.push(
          <span key={`s${i}`} className="text-[var(--color-ink-primary)]">
            {m[1]}
          </span>,
        )
      }
    } else if (m[2]) {
      out.push(
        <span key={`n${i}`} className="text-[var(--color-amber-400)]">
          {m[2]}
        </span>,
      )
    } else if (m[3]) {
      out.push(
        <span key={`l${i}`} className="text-[var(--color-ink-tertiary)] italic">
          {m[3]}
        </span>,
      )
    }
    last = TOKEN.lastIndex
    i++
  }
  if (last < input.length) out.push(input.slice(last))
  return out
}
