import { useState } from 'react'
import type { ExtractionResult } from '../types'

interface Props {
  result: ExtractionResult
}

type ViewMode = 'json' | 'table'

export function ResultsViewer({ result }: Props) {
  const [mode, setMode] = useState<ViewMode>('json')
  const [copied, setCopied] = useState(false)

  const jsonString = JSON.stringify(result.data ?? {}, null, 2)

  const handleCopy = () => {
    void navigator.clipboard.writeText(jsonString).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const entries = result.data ? Object.entries(result.data) : []

  const statusColor =
    result.status === 'completed' ? 'text-emerald-400' :
    result.status === 'completed_with_errors' ? 'text-amber-400' :
    'text-red-400'

  return (
    <div className="space-y-5">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Status', value: result.status.replaceAll('_', ' '), colorClass: statusColor },
          { label: 'Time', value: `${result.processing_time_ms}ms` },
          { label: 'Chunks', value: String(result.chunks_processed) },
          { label: 'Retries', value: String(result.retries_used) },
        ].map(({ label, value, colorClass }) => (
          <div key={label} className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3">
            <p className="text-xs text-zinc-600 mb-1">{label}</p>
            <p className={`text-sm font-medium font-mono ${colorClass ?? 'text-zinc-200'}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Model badge */}
      <p className="text-xs text-zinc-600 font-mono">
        Extracted with <span className="text-zinc-400">{result.model_used}</span>
        {result.validation_passed
          ? <span className="ml-2 text-emerald-600">· validation passed</span>
          : <span className="ml-2 text-amber-600">· validation issues</span>}
      </p>

      {/* View toggle + copy */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-zinc-900 border border-zinc-800">
          {(['json', 'table'] as ViewMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors
                ${mode === m ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
            >
              {m === 'json' ? 'JSON' : 'Table'}
            </button>
          ))}
        </div>
        <button
          onClick={handleCopy}
          className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors px-3 py-1
                     rounded-lg border border-zinc-800 hover:border-zinc-600"
        >
          {copied ? '✓ Copied' : 'Copy JSON'}
        </button>
      </div>

      {/* Data view */}
      {mode === 'json' ? (
        <pre className="rounded-xl bg-zinc-900 border border-zinc-800 p-5 text-sm font-mono
                        text-zinc-300 overflow-auto max-h-[500px] leading-relaxed">
          {result.data ? jsonString : <span className="text-zinc-600">No data extracted</span>}
        </pre>
      ) : (
        <div className="rounded-xl border border-zinc-800 overflow-hidden">
          {entries.length === 0 ? (
            <p className="p-5 text-sm text-zinc-600">No data extracted</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-zinc-900 border-b border-zinc-800">
                  <th className="text-left px-5 py-3 font-medium text-zinc-400 w-1/3">Field</th>
                  <th className="text-left px-5 py-3 font-medium text-zinc-400">Value</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([key, val], i) => (
                  <tr
                    key={key}
                    className={i % 2 === 0 ? 'bg-zinc-950' : 'bg-zinc-900/50'}
                  >
                    <td className="px-5 py-3 font-mono text-xs text-zinc-400 align-top">{key}</td>
                    <td className="px-5 py-3 font-mono text-xs text-zinc-200 break-all">
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
    </div>
  )
}
