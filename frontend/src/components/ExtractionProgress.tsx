import { useEffect, useMemo, useRef } from 'react'
import type { StreamEvent } from '../types'
import type { SSEStatus } from '../hooks/useSSE'

// Mirrors the real LangGraph pipeline in backend/app/workflows/graph.py.
const NODES = [
  { id: 'parse',            label: 'parse' },
  { id: 'chunk',            label: 'chunk' },
  { id: 'extract',          label: 'extract' },
  { id: 'consolidate',      label: 'consolidate' },
  { id: 'verify_grounding', label: 'grounding' },
  { id: 'validate',         label: 'validate' },
  { id: 'finalize',         label: 'finalize' },
] as const

type NodeId = (typeof NODES)[number]['id']

// Nodes that run again on every retry pass (validate → extract loop).
const LOOP_NODES: ReadonlySet<string> = new Set(['extract', 'consolidate', 'verify_grounding', 'validate', 'finalize'])

const MAX_RETRIES = 3
const STICK_THRESHOLD_PX = 24

type RowState = 'done' | 'active' | 'pending' | 'success' | 'error' | 'retry' | 'retry-detail'

interface LogRow {
  key: string
  bullet: '▸' | '●' | '✓' | '✕' | '·' | '↻' | ' '
  offset: string
  node: string
  message: string
  state: RowState
  /** Full text for a truncated message — rendered as the row's title attribute */
  title?: string
}

const ROW_TEXT: Record<RowState, string> = {
  done: 'text-[var(--color-ink-secondary)]',
  active: 'text-[var(--color-ember-200)]',
  pending: 'text-[var(--color-ink-quaternary)]',
  success: 'text-[var(--color-ember-400)]',
  error: 'text-[var(--color-rust-400)]',
  retry: 'text-[var(--color-amber-400)]',
  'retry-detail': 'text-[var(--color-amber-400)]/70 text-[12px]',
}

const ROW_BULLET: Record<RowState, string> = {
  done: 'text-[var(--color-ink-tertiary)]',
  active: 'text-[var(--color-ember-500)] ember-pulse',
  pending: 'text-[var(--color-ink-quaternary)]',
  success: 'text-[var(--color-ember-500)]',
  error: 'text-[var(--color-rust-500)]',
  retry: 'text-[var(--color-amber-400)]',
  'retry-detail': '',
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

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function stringList(data: Record<string, unknown> | null, key: string): string[] | null {
  const value = data?.[key]
  return Array.isArray(value) ? value.map(String) : null
}

/** Human message for a completed node — what happened, not just that it finished. */
function nodeMessage(e: StreamEvent): string {
  const data = e.data
  switch (e.node) {
    case 'chunk':
    case 'extract': {
      const n = data?.chunks
      return typeof n === 'number' ? plural(n, 'chunk') : e.message
    }
    case 'verify_grounding': {
      const issues = stringList(data, 'issues')
      if (issues === null) return e.message
      return issues.length === 0 ? 'all values grounded' : `${issues.length} rejected`
    }
    case 'validate': {
      const errors = stringList(data, 'errors')
      if (errors === null) return e.message
      return errors.length === 0 ? 'ok' : plural(errors.length, 'issue')
    }
    default:
      return e.message
  }
}

interface DerivedLog {
  rows: LogRow[]
  activeNode: NodeId | null
  retryCount: number
}

function buildLog(events: StreamEvent[], status: SSEStatus, error: string | null): DerivedLog {
  const nodeEvents = events.filter((e) => e.event === 'node_completed' && e.node)
  const retryEvents = events.filter((e) => e.event === 'retry')
  const doneEvent = events.find((e) => e.event === 'done') ?? null
  const errorMsg = events.find((e) => e.event === 'error')?.message ?? error

  const t0 = events[0] ? new Date(events[0].timestamp).getTime() : null
  const offsetOf = (e: StreamEvent) =>
    t0 !== null ? formatOffset(new Date(e.timestamp).getTime() - t0) : '+00:00.0'

  // Prefer explicit retry events; fall back to counting validate passes for
  // streams from a backend that does not emit them.
  const validatePasses = nodeEvents.filter((e) => e.node === 'validate').length
  const retryCount = retryEvents.length > 0 ? retryEvents.length : Math.max(0, validatePasses - 1)

  // "Completed" for the purpose of what runs next: after a retry the loop
  // nodes run again, so only completions since the last retry count for them.
  const lastRetryIdx = events.findLastIndex((e) => e.event === 'retry')
  const completed = new Set<string>()
  events.forEach((e, i) => {
    if (e.event !== 'node_completed' || !e.node) return
    if (LOOP_NODES.has(e.node) && i < lastRetryIdx) return
    completed.add(e.node)
  })

  const activeNode: NodeId | null =
    status === 'streaming' || status === 'connecting'
      ? NODES.find((n) => !completed.has(n.id))?.id ?? null
      : null

  // Latest within-node progress (e.g. extract 3/7) for the active node, if any.
  const activeProgress =
    activeNode !== null
      ? events.filter((e) => e.event === 'progress' && e.node === activeNode).at(-1) ?? null
      : null

  const rows: LogRow[] = []

  events.forEach((e, i) => {
    if (e.event === 'node_completed' && e.node) {
      rows.push({
        key: `node-${i}-${e.node}`,
        bullet: '▸',
        offset: offsetOf(e),
        node: e.node,
        message: nodeMessage(e),
        state: 'done',
      })
    } else if (e.event === 'retry') {
      const attempt = typeof e.data?.attempt === 'number' ? e.data.attempt : retryEvents.indexOf(e) + 1
      rows.push({
        key: `retry-${i}`,
        bullet: '↻',
        offset: offsetOf(e),
        node: 'retry',
        message: `attempt ${attempt} failed — retrying`,
        state: 'retry',
      })
      for (const [j, err] of (stringList(e.data, 'errors') ?? []).entries()) {
        rows.push({
          key: `retry-${i}-err-${j}`,
          bullet: ' ',
          offset: '',
          node: '',
          message: `↳ ${err}`,
          title: err,
          state: 'retry-detail',
        })
      }
    }
  })

  if (activeNode && !doneEvent && status !== 'error') {
    rows.push({
      key: `active-${activeNode}`,
      bullet: '●',
      // Render an empty timestamp slot — the active offset would otherwise change
      // every render via Date.now() and churn React reconciliation for no reason.
      offset: '         ',
      node: activeNode,
      message:
        status === 'connecting'
          ? 'connecting…'
          : activeProgress
          ? `${activeProgress.data?.completed ?? '?'}/${activeProgress.data?.total ?? '?'}`
          : 'running…',
      state: 'active',
    })
  }

  if (doneEvent) {
    rows.push({
      key: 'done',
      bullet: '✓',
      offset: t0 !== null ? offsetOf(doneEvent) : '',
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
              title={row.title}
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
