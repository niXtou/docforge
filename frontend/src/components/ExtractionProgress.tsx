import { useEffect, useMemo, useRef } from 'react'
import type { StreamEvent } from '../types'
import type { SSEStatus } from '../hooks/useSSE'

const NODES = [
  { id: 'parse',    label: 'parse' },
  { id: 'chunk',    label: 'chunk' },
  { id: 'extract',  label: 'extract' },
  { id: 'validate', label: 'validate' },
  { id: 'merge',    label: 'merge' },
] as const

type NodeId = (typeof NODES)[number]['id']

const MAX_RETRIES = 3
const STICK_THRESHOLD_PX = 24

type RowState = 'done' | 'active' | 'pending' | 'success' | 'error'

interface LogRow {
  key: string
  bullet: '▸' | '●' | '✓' | '✕' | '·'
  offset: string
  node: string
  message: string
  state: RowState
}

const ROW_TEXT: Record<RowState, string> = {
  done: 'text-[var(--color-ink-secondary)]',
  active: 'text-[var(--color-ember-200)]',
  pending: 'text-[var(--color-ink-quaternary)]',
  success: 'text-[var(--color-ember-400)]',
  error: 'text-[var(--color-rust-400)]',
}

const ROW_BULLET: Record<RowState, string> = {
  done: 'text-[var(--color-ink-tertiary)]',
  active: 'text-[var(--color-ember-500)] ember-pulse',
  pending: 'text-[var(--color-ink-quaternary)]',
  success: 'text-[var(--color-ember-500)]',
  error: 'text-[var(--color-rust-500)]',
}

interface Props {
  events: StreamEvent[]
  status: SSEStatus
  error: string | null
}

function formatOffset(ms: number): string {
  const totalSeconds = ms / 1000
  const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const s = (totalSeconds % 60).toFixed(1).padStart(4, '0')
  return `+${m}:${s}`
}

interface DerivedLog {
  rows: LogRow[]
  activeNode: NodeId | null
  retryCount: number
}

function buildLog(events: StreamEvent[], status: SSEStatus, error: string | null): DerivedLog {
  const nodeEvents = events.filter((e) => e.event === 'node_completed' && e.node)
  const doneEvent = events.find((e) => e.event === 'done') ?? null
  const errorMsg = events.find((e) => e.event === 'error')?.message ?? error

  const t0 = events[0] ? new Date(events[0].timestamp).getTime() : null
  const completed = new Set<string>(nodeEvents.map((e) => e.node!))
  const retryCount = nodeEvents.filter((e) => e.node === 'validate').length - 1

  const activeNode: NodeId | null =
    status === 'streaming' || status === 'connecting'
      ? NODES.find((n) => !completed.has(n.id))?.id ?? null
      : null

  const rows: LogRow[] = []

  nodeEvents.forEach((e, i) => {
    const offset = t0 !== null ? formatOffset(new Date(e.timestamp).getTime() - t0) : '+00:00.0'
    rows.push({
      key: `node-${i}-${e.node}`,
      bullet: '▸',
      offset,
      node: e.node!,
      message: e.message,
      state: 'done',
    })
  })

  if (activeNode && !doneEvent && status !== 'error') {
    rows.push({
      key: `active-${activeNode}`,
      bullet: '●',
      // Render an empty timestamp slot — the active offset would otherwise change
      // every render via Date.now() and churn React reconciliation for no reason.
      offset: '         ',
      node: activeNode,
      message: status === 'connecting' ? 'connecting…' : 'running…',
      state: 'active',
    })
  }

  if (doneEvent) {
    const offset = t0 !== null ? formatOffset(new Date(doneEvent.timestamp).getTime() - t0) : ''
    rows.push({
      key: 'done',
      bullet: '✓',
      offset,
      node: 'done',
      message: doneEvent.message || 'extraction complete',
      state: 'success',
    })
  } else if (status === 'error') {
    rows.push({
      key: 'error',
      bullet: '✕',
      offset: '',
      node: 'error',
      message: errorMsg || 'extraction failed',
      state: 'error',
    })
  }

  if (!doneEvent && status !== 'error') {
    for (const n of NODES) {
      if (!completed.has(n.id) && n.id !== activeNode) {
        rows.push({
          key: `pending-${n.id}`,
          bullet: '·',
          offset: '         ',
          node: n.label,
          message: '—',
          state: 'pending',
        })
      }
    }
  }

  return { rows, activeNode, retryCount }
}

export function ExtractionProgress({ events, status, error }: Props) {
  const logRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)

  const { rows, activeNode, retryCount } = useMemo(
    () => buildLog(events, status, error),
    [events, status, error],
  )

  const onScroll = () => {
    const el = logRef.current
    if (!el) return
    stickToBottomRef.current = el.scrollHeight - (el.scrollTop + el.clientHeight) < STICK_THRESHOLD_PX
  }

  useEffect(() => {
    if (!stickToBottomRef.current) return
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [rows.length])

  const sweepActive = status === 'streaming' || status === 'connecting'
  const headerLabel = status === 'done' ? 'done' : status === 'error' ? 'failed' : activeNode ?? 'starting'
  const headerDot =
    status === 'done'
      ? 'bg-[var(--color-ember-400)]'
      : status === 'error'
      ? 'bg-[var(--color-rust-400)]'
      : 'bg-[var(--color-ember-500)] ember-pulse'

  return (
    <div className="relative card-panel overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-px">
        {sweepActive ? (
          <div className="h-full ember-sweep" />
        ) : status === 'done' ? (
          <div className="h-full bg-[var(--color-ember-500)]/60" />
        ) : status === 'error' ? (
          <div className="h-full bg-[var(--color-rust-500)]/60" />
        ) : (
          <div className="h-full bg-[var(--color-hairline)]" />
        )}
      </div>

      <div className="flex items-center justify-between px-5 py-3.5 border-b border-hairline">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className={`inline-block w-1.5 h-1.5 rounded-full ${headerDot}`} />
          <span className="mono-cap text-[var(--color-ink-secondary)]">{headerLabel}</span>
        </div>

        {retryCount > 0 && (
          <span className="mono-cap-sm text-[var(--color-amber-400)] border border-[var(--color-amber-400)]/30 rounded px-2 py-0.5">
            retried · {retryCount} of {MAX_RETRIES}
          </span>
        )}
      </div>

      <div
        ref={logRef}
        onScroll={onScroll}
        className="font-mono text-[13px] leading-[1.7] px-5 py-4 max-h-[420px] overflow-y-auto"
      >
        {rows.map((row, i) => {
          const isLast = i === rows.length - 1
          return (
            <div
              key={row.key}
              className={`grid grid-cols-[1ch_minmax(0,7ch)_minmax(0,12ch)_1fr] gap-x-3 ${ROW_TEXT[row.state]} ${
                row.state !== 'pending' && isLast ? 'row-enter' : ''
              }`}
            >
              <span className={`select-none ${ROW_BULLET[row.state]}`}>{row.bullet}</span>
              <span className="text-[var(--color-ink-quaternary)] whitespace-pre">{row.offset}</span>
              <span className="truncate">{row.node}</span>
              <span className="truncate">{row.message}</span>
            </div>
          )
        })}
        {rows.length === 0 && (
          <div className="text-[var(--color-ink-tertiary)] italic">connecting to stream…</div>
        )}
      </div>
    </div>
  )
}
