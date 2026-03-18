import { useEffect, useState } from 'react'
import { listSchemas } from '../api/client'
import type { Schema } from '../types'

interface Props {
  value: Schema | null
  onChange: (schema: Schema | null) => void
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
      <div className="h-10 rounded-lg bg-zinc-800 animate-pulse" role="status" aria-label="Loading schemas" />
    )
  }
  if (error) {
    return <p className="text-sm text-red-400">Failed to load schemas: {error}</p>
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-zinc-300">
        Extraction Schema
      </label>
      <div className="flex gap-2">
        <select
          className="flex-1 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-100
                     px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500
                     focus:border-transparent"
          value={value?.id ?? ''}
          onChange={(e) => {
            const schema = schemas.find((s) => s.id === Number(e.target.value)) ?? null
            onChange(schema)
          }}
        >
          <option value="">Select a schema…</option>
          {schemas.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.is_builtin ? ' ✦' : ''}
            </option>
          ))}
        </select>
        {value && (
          <button
            type="button"
            onClick={() => setViewing(value)}
            className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-sm
                       text-zinc-300 hover:text-zinc-100 hover:border-zinc-600 transition-colors"
            aria-label="View schema JSON"
          >
            View
          </button>
        )}
      </div>
      {value?.description && (
        <p className="text-xs text-zinc-500">{value.description}</p>
      )}

      {/* Schema viewer modal */}
      {viewing && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setViewing(null)}
        >
          <div
            className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl max-w-xl w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <h3 className="font-semibold text-zinc-100">{viewing.name}</h3>
              <button
                onClick={() => setViewing(null)}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <pre className="px-5 py-4 text-xs font-mono text-zinc-300 overflow-auto max-h-96">
              {JSON.stringify(viewing.json_schema, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
