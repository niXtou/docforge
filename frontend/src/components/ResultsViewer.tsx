import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { highlightJson } from '../lib/highlightJson'
import type { ExtractionResult } from '../types'

interface Props {
  result: ExtractionResult
}

type ViewMode = 'json' | 'table'

const TABS: { id: ViewMode; label: string }[] = [
  { id: 'json', label: 'JSON' },
  { id: 'table', label: 'Table' },
]

const STATUS_TONE: Record<ExtractionResult['status'], string> = {
  completed: 'text-[var(--color-ember-400)]',
  completed_with_errors: 'text-[var(--color-amber-400)]',
  failed: 'text-[var(--color-rust-400)]',
}

const COPY_FEEDBACK_MS = 1400

export function ResultsViewer({ result }: Props) {
  const [mode, setMode] = useState<ViewMode>('json')
  const [copied, setCopied] = useState(false)
  const tabRefs = useRef<Partial<Record<ViewMode, HTMLButtonElement | null>>>({})
  const indicatorRef = useRef<HTMLSpanElement>(null)

  const jsonString = useMemo(() => JSON.stringify(result.data ?? {}, null, 2), [result.data])
  const highlighted = useMemo(() => (result.data ? highlightJson(jsonString) : null), [result.data, jsonString])

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
      </p>

      {result.status === 'failed' && result.error_message && (
        <div className="rounded-md border border-[var(--color-rust-500)]/60 bg-[var(--color-rust-500)]/10 px-4 py-3">
          <p className="mono-cap-sm text-[var(--color-rust-400)] mb-1.5">extraction failed</p>
          <p className="text-sm font-mono text-[var(--color-rust-400)] break-words leading-relaxed">
            {result.error_message}
          </p>
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
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="text-left px-5 py-3 mono-cap-sm text-[var(--color-ink-tertiary)] w-1/3">
                    field
                  </th>
                  <th className="text-left px-5 py-3 mono-cap-sm text-[var(--color-ink-tertiary)]">
                    value
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([key, val], i) => (
                  <tr key={key} className={i > 0 ? 'border-t border-hairline' : ''}>
                    <td className="px-5 py-3 font-mono text-[12px] text-[var(--color-ember-400)] align-top">
                      {key}
                    </td>
                    <td className="px-5 py-3 font-mono text-[12px] text-[var(--color-ink-primary)] break-all">
                      {Array.isArray(val)
                        ? val.join(', ')
                        : typeof val === 'object' && val !== null
                        ? JSON.stringify(val)
                        : String(val ?? '–')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
