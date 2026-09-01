import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { highlightJson } from '../lib/highlightJson'
import type { ExtractionResult, FieldEvidence } from '../types'

interface Props {
  result: ExtractionResult
}

type ViewMode = 'table' | 'json'

// Table first: it is the view that carries the evidence column.
const TABS: { id: ViewMode; label: string }[] = [
  { id: 'table', label: 'Table' },
  { id: 'json', label: 'JSON' },
]

const STATUS_TONE: Record<ExtractionResult['status'], string> = {
  completed: 'text-[var(--color-ember-400)]',
  completed_with_errors: 'text-[var(--color-amber-400)]',
  failed: 'text-[var(--color-rust-400)]',
}

const METHOD_TONE: Record<FieldEvidence['method'], string> = {
  verbatim: 'text-[var(--color-ember-400)] border-[var(--color-ember-500)]/40',
  judge: 'text-[var(--color-amber-400)] border-[var(--color-amber-400)]/40',
  unverified: 'text-[var(--color-ink-tertiary)] border-hairline-strong',
}

const COPY_FEEDBACK_MS = 1400

function formatValue(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'object' && val !== null) return JSON.stringify(val)
  return String(val ?? '–')
}

function MethodBadge({ method }: { method: FieldEvidence['method'] }) {
  return (
    <span className={`mono-cap-sm border rounded px-1.5 py-px shrink-0 ${METHOD_TONE[method]}`}>
      {method}
    </span>
  )
}

interface EvidenceLine {
  /** "field[i]" label for array items; omitted for scalars */
  label?: string
  evidence: FieldEvidence | undefined
}

function EvidenceCell({ lines }: { lines: EvidenceLine[] }) {
  return (
    <div className="space-y-1.5">
      {lines.map(({ label, evidence }, i) => (
        <div key={label ?? i} className="flex items-start gap-2 min-w-0">
          {label && (
            <span className="font-mono text-[11px] text-[var(--color-ink-quaternary)] shrink-0 pt-px">
              {label}
            </span>
          )}
          {evidence ? (
            <>
              <MethodBadge method={evidence.method} />
              {evidence.supported ? (
                <span className="italic text-[12px] text-[var(--color-ink-secondary)] break-words min-w-0">
                  {evidence.quote || '—'}
                </span>
              ) : (
                <span className="text-[12px] text-[var(--color-rust-400)]">rejected</span>
              )}
            </>
          ) : (
            <span className="text-[12px] text-[var(--color-ink-quaternary)]">—</span>
          )}
        </div>
      ))}
    </div>
  )
}

/** Evidence lines for one field: one per array item, or a single line for a scalar. */
function evidenceLines(
  key: string,
  val: unknown,
  evidence: Record<string, FieldEvidence>,
): EvidenceLine[] {
  const lines: EvidenceLine[] = Array.isArray(val)
    ? val.map((_, i) => ({ label: `${key}[${i}]`, evidence: evidence[`${key}[${i}]`] }))
    : [{ evidence: evidence[key] }]
  // Items the judge dropped are keyed "field[dropped:<original i>]".
  const droppedPrefix = `${key}[dropped:`
  for (const k of Object.keys(evidence)) {
    if (k.startsWith(droppedPrefix)) lines.push({ label: k.slice(key.length), evidence: evidence[k] })
  }
  return lines
}

export function ResultsViewer({ result }: Props) {
  const [mode, setMode] = useState<ViewMode>('table')
  const [copied, setCopied] = useState(false)
  const tabRefs = useRef<Partial<Record<ViewMode, HTMLButtonElement | null>>>({})
  const indicatorRef = useRef<HTMLSpanElement>(null)

  // JSON is the raw extraction — evidence is provenance, not data, so it stays out.
  const jsonString = useMemo(() => JSON.stringify(result.data ?? {}, null, 2), [result.data])
  const highlighted = useMemo(() => (result.data ? highlightJson(jsonString) : null), [result.data, jsonString])

  const evidence = useMemo(() => result.evidence ?? {}, [result.evidence])
  const validationErrors = result.validation_errors ?? []
  const { grounded, total } = useMemo(() => {
    const entries = Object.values(evidence)
    return {
      grounded: entries.filter((e) => e.method !== 'unverified' && e.supported).length,
      total: entries.length,
    }
  }, [evidence])

  const handleCopy = () => {
    void navigator.clipboard.writeText(jsonString).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), COPY_FEEDBACK_MS)
    })
  }

  // Position the active-tab underline by writing directly to the ref — avoids an
  // extra state-driven render per tab switch.
  useLayoutEffect(() => {
    const btn = tabRefs.current[mode]
    const ind = indicatorRef.current
    if (btn && ind) {
      ind.style.left = `${btn.offsetLeft}px`
      ind.style.width = `${btn.offsetWidth}px`
    }
  }, [mode])

  const entries = result.data ? Object.entries(result.data) : []

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[var(--color-hairline)] border border-hairline-strong rounded-lg overflow-hidden">
        {[
          { label: 'status', value: result.status.replaceAll('_', ' '), tone: STATUS_TONE[result.status] },
          { label: 'time', value: `${result.processing_time_ms}ms`, tone: '' },
          { label: 'chunks', value: String(result.chunks_processed), tone: '' },
          { label: 'retries', value: String(result.retries_used), tone: '' },
        ].map(({ label, value, tone }) => (
          <div key={label} className="bg-[var(--color-surface-1)] px-4 py-3.5">
            <p className="mono-cap-sm text-[var(--color-ink-tertiary)] mb-1.5">{label}</p>
            <p className={`font-mono text-[13px] ${tone || 'text-[var(--color-ink-primary)]'}`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      <p className="mono-cap text-[var(--color-ink-tertiary)]">
        model:{' '}
        <span className="text-[var(--color-ink-secondary)] normal-case tracking-normal text-[12px]">
          {result.model_used}
        </span>
        <span aria-hidden="true" className="mx-2 text-[var(--color-ink-quaternary)]">·</span>
        {result.validation_passed ? (
          <span className="text-[var(--color-ember-400)]">validation passed</span>
        ) : (
          <span className="text-[var(--color-amber-400)]">validation issues</span>
        )}
        {total > 0 && (
          <>
            <span aria-hidden="true" className="mx-2 text-[var(--color-ink-quaternary)]">·</span>
            <span className={grounded === total ? 'text-[var(--color-ember-400)]' : 'text-[var(--color-ink-secondary)]'}>
              {grounded} of {total} values grounded
            </span>
          </>
        )}
      </p>

      {result.status === 'failed' && result.error_message && (
        <div className="rounded-md border border-[var(--color-rust-500)]/60 bg-[var(--color-rust-500)]/10 px-4 py-3">
          <p className="mono-cap-sm text-[var(--color-rust-400)] mb-1.5">extraction failed</p>
          <p className="text-sm font-mono text-[var(--color-rust-400)] break-words leading-relaxed">
            {result.error_message}
          </p>
        </div>
      )}

      {validationErrors.length > 0 && (
        <div
          role="region"
          aria-label="Validation issues"
          className="rounded-md border border-[var(--color-amber-400)]/40 bg-[var(--color-amber-400)]/[0.06] px-4 py-3"
        >
          <p className="mono-cap-sm text-[var(--color-amber-400)] mb-2">
            validation issues · {validationErrors.length}
          </p>
          <ul className="space-y-1 font-mono text-[12px] leading-relaxed text-[var(--color-amber-400)]/80">
            {validationErrors.map((err, i) => (
              <li key={i} className="break-words">
                {err}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between border-b border-hairline">
        <div className="relative flex">
          {TABS.map((t) => (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[t.id] = el
              }}
              onClick={() => setMode(t.id)}
              className={`px-4 py-2.5 mono-cap transition-colors duration-150 ${
                mode === t.id
                  ? 'text-[var(--color-ink-primary)]'
                  : 'text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)]'
              }`}
            >
              {t.label}
            </button>
          ))}
          <span
            ref={indicatorRef}
            aria-hidden="true"
            className="absolute bottom-[-1px] h-px bg-[var(--color-ember-500)]
                       transition-all duration-200 [transition-timing-function:var(--ease-out-soft)]"
          />
        </div>
        <button
          onClick={handleCopy}
          className="mono-cap text-[var(--color-ink-tertiary)] hover:text-[var(--color-ember-400)]
                     transition-colors duration-150 px-2"
        >
          {copied ? <span className="text-[var(--color-ember-400)]">copied</span> : 'copy'}
        </button>
      </div>

      {mode === 'json' ? (
        <pre className="card-panel p-5 text-[13px] font-mono leading-[1.7]
                        text-[var(--color-ink-secondary)] overflow-auto max-h-[500px]">
          {highlighted ?? <span className="text-[var(--color-ink-tertiary)] italic">No data extracted</span>}
        </pre>
      ) : (
        <div className="card-panel overflow-hidden">
          {entries.length === 0 ? (
            <p className="p-5 text-sm text-[var(--color-ink-tertiary)] italic">No data extracted</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline">
                    <th className="text-left px-5 py-3 mono-cap-sm text-[var(--color-ink-tertiary)] w-1/5">
                      field
                    </th>
                    <th className="text-left px-5 py-3 mono-cap-sm text-[var(--color-ink-tertiary)] w-2/5">
                      value
                    </th>
                    <th className="text-left px-5 py-3 mono-cap-sm text-[var(--color-ink-tertiary)]">
                      evidence
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map(([key, val], i) => (
                    <tr key={key} className={i > 0 ? 'border-t border-hairline' : ''}>
                      <td className="px-5 py-3 font-mono text-[12px] text-[var(--color-ember-400)] align-top">
                        {key}
                      </td>
                      <td className="px-5 py-3 font-mono text-[12px] text-[var(--color-ink-primary)] break-all align-top">
                        {formatValue(val)}
                      </td>
                      <td className="px-5 py-3 align-top">
                        <EvidenceCell lines={evidenceLines(key, val, evidence)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {result.retries_used > 0 && (
        <p className="font-mono text-[11px] text-[var(--color-ink-tertiary)] italic">
          extracted on attempt {result.retries_used + 1}
          {' · '}
          {result.retries_used} retr{result.retries_used === 1 ? 'y' : 'ies'} needed
        </p>
      )}
    </div>
  )
}
