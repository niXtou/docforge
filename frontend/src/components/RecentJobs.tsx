import { useEffect, useState } from 'react'
import { listJobs } from '../api/client'
import type { ExtractionJobSummary } from '../types'

interface Props {
  /** Called with a terminal job when its row is clicked */
  onOpen: (job: ExtractionJobSummary) => void
}

const TERMINAL: ReadonlySet<string> = new Set(['completed', 'completed_with_errors', 'failed'])

const STATUS_TONE: Record<string, string> = {
  completed: 'text-[var(--color-ember-400)]',
  completed_with_errors: 'text-[var(--color-amber-400)]',
  failed: 'text-[var(--color-rust-400)]',
}

/**
 * The backend stores timestamps without a zone (UTC) and serialises them
 * without a "Z", which `Date` would otherwise read as local time.
 */
function parseServerDate(iso: string): number {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`).getTime()
}

function relativeTime(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - parseServerDate(iso)) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

export function RecentJobs({ onOpen }: Props) {
  const [jobs, setJobs] = useState<ExtractionJobSummary[]>([])

  useEffect(() => {
    // Hidden entirely when there is nothing to show or the request fails —
    // history is a convenience, never a reason to block the form.
    listJobs()
      .then(setJobs)
      .catch(() => setJobs([]))
  }, [])

  if (jobs.length === 0) return null

  return (
    <section className="mt-10" aria-label="Recent jobs">
      <div className="flex items-baseline justify-between mb-3">
        <span className="mono-cap text-[var(--color-ink-tertiary)]">Recent jobs</span>
        <span className="mono-cap-sm text-[var(--color-ink-quaternary)]">click a finished job to reopen it</span>
      </div>
      <div className="card-panel divide-y divide-[var(--color-hairline)] overflow-hidden">
        {jobs.map((job) => {
          const terminal = TERMINAL.has(job.status)
          const row = (
            <div
              className="grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,9ch)_minmax(0,5ch)_minmax(0,8ch)] gap-x-4 items-baseline
                         font-mono text-[12px] px-4 py-2.5"
            >
              <span className="truncate text-[var(--color-ink-primary)]" title={job.original_filename}>
                {job.original_filename}
              </span>
              <span className="truncate text-[var(--color-ink-secondary)]">{job.schema_name}</span>
              <span className={`truncate ${STATUS_TONE[job.status] ?? 'text-[var(--color-ink-tertiary)]'}`}>
                {job.status.replaceAll('_', ' ')}
              </span>
              <span className="text-[var(--color-ink-tertiary)] text-right">
                {job.retries_used > 0 ? `↻ ${job.retries_used}` : ''}
              </span>
              <span className="text-[var(--color-ink-tertiary)] text-right">{relativeTime(job.created_at)}</span>
            </div>
          )
          return terminal ? (
            <button
              key={job.job_id}
              type="button"
              onClick={() => onOpen(job)}
              className="block w-full text-left hover:bg-[var(--color-surface-2)] transition-colors duration-150
                         focus:outline-none focus-visible:bg-[var(--color-surface-2)]"
            >
              {row}
            </button>
          ) : (
            <div key={job.job_id} className="opacity-50 cursor-default" aria-disabled="true">
              {row}
            </div>
          )
        })}
      </div>
    </section>
  )
}
