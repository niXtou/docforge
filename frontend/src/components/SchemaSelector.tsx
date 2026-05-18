import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { listSchemas } from '../api/client'
import { highlightJson } from '../lib/highlightJson'
import type { Schema } from '../types'
import { FieldLabel } from './FieldLabel'

interface Props {
  value: Schema | null
  onChange: (schema: Schema | null) => void
}

function Chevron() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 12 8"
      className="absolute right-3.5 top-1/2 -translate-y-1/2 w-2.5 h-1.5 pointer-events-none stroke-[var(--color-ink-secondary)]"
      fill="none"
      strokeWidth="1.5"
    >
      <path d="M1 1.5l5 5 5-5" />
    </svg>
  )
}

export function SchemaSelector({ value, onChange }: Props) {
  const [schemas, setSchemas] = useState<Schema[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewing, setViewing] = useState<Schema | null>(null)

  useEffect(() => {
    listSchemas()
      .then(setSchemas)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div
        className="h-10 rounded-md bg-[var(--color-surface-2)] animate-pulse"
        role="status"
        aria-label="Loading schemas"
      />
    )
  }
  if (error) {
    return <p className="text-sm text-[var(--color-rust-400)]">Failed to load schemas: {error}</p>
  }

  return (
    <div className="space-y-2">
      <FieldLabel>Schema</FieldLabel>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <select
            className="w-full appearance-none rounded-md bg-[var(--color-surface-2)] border border-hairline-strong
                       text-[var(--color-ink-primary)] pl-3.5 pr-10 py-2.5 text-sm cursor-pointer
                       transition-shadow duration-150
                       focus:outline-none focus:glow-ember-soft focus:border-transparent"
            value={value?.id ?? ''}
            onChange={(e) => {
              const schema = schemas.find((s) => s.id === Number(e.target.value)) ?? null
              onChange(schema)
            }}
          >
            <option value="">Select a schema…</option>
            {schemas.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name === 'Research Paper' ? `${s.name} (work in progress)` : s.name}
              </option>
            ))}
          </select>
          <Chevron />
        </div>
        {value && (
          <button
            type="button"
            onClick={() => setViewing(value)}
            className="px-3.5 py-2.5 rounded-md border border-hairline-strong text-sm
                       text-[var(--color-ink-secondary)] hover:text-[var(--color-ink-primary)]
                       hover:border-[var(--color-ember-500)]/40 transition-colors duration-150"
            aria-label="View schema JSON"
          >
            View
          </button>
        )}
      </div>
      {value?.description && (
        <p className="text-xs text-[var(--color-ink-tertiary)] leading-relaxed">{value.description}</p>
      )}

      {/* Portal-render the modal so ancestor transforms (e.g. .step-enter) don't capture
          its `fixed inset-0` overlay and shrink it to the centered column. */}
      {viewing &&
        createPortal(
          <div
            className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
            onClick={() => setViewing(null)}
          >
            <div
              className="card-panel max-w-xl w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-hairline">
                <h3 className="font-serif text-[1.05rem] font-medium text-[var(--color-ink-primary)]">
                  {viewing.name}
                </h3>
                <button
                  onClick={() => setViewing(null)}
                  className="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] transition-colors duration-150 text-sm"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>
              <pre className="px-5 py-4 text-[13px] font-mono text-[var(--color-ink-secondary)] overflow-auto max-h-96 leading-[1.7]">
                {highlightJson(JSON.stringify(viewing.json_schema, null, 2))}
              </pre>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
