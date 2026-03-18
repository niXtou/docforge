import type { StreamEvent } from '../types'
import type { SSEStatus } from '../hooks/useSSE'

// The fixed node execution order (matches graph.py)
const NODES = [
  { id: 'parse',    label: 'Parse',    description: 'Reading document' },
  { id: 'chunk',    label: 'Chunk',    description: 'Splitting text' },
  { id: 'extract',  label: 'Extract',  description: 'LLM extraction' },
  { id: 'validate', label: 'Validate', description: 'Checking fields' },
  { id: 'merge',    label: 'Merge',    description: 'Finalizing result' },
] as const

interface Props {
  events: StreamEvent[]
  status: SSEStatus
  error: string | null
}

export function ExtractionProgress({ events, status, error }: Props) {
  // Collect which nodes have completed and count retries (validate > 1)
  const completedNodes = new Set(
    events.filter((e) => e.event === 'node_completed' && e.node).map((e) => e.node!),
  )
  const retryCount = events.filter((e) => e.event === 'node_completed' && e.node === 'validate').length - 1

  const isActiveNode = (nodeId: string): boolean => {
    if (status === 'streaming') {
      // The active node is the one immediately after the last completed node
      const completedOrder = NODES.map((n) => n.id).filter((id) => completedNodes.has(id))
      const lastCompleted = completedOrder.at(-1)
      if (!lastCompleted) return nodeId === 'parse'
      const lastIndex = NODES.findIndex((n) => n.id === lastCompleted)
      return NODES[lastIndex + 1]?.id === nodeId
    }
    return false
  }

  return (
    <div className="space-y-6">
      {/* Status banner */}
      <div className="flex items-center gap-3">
        {status === 'done' ? (
          <div className="flex items-center gap-2 text-emerald-400">
            <span className="text-lg">✓</span>
            <span className="font-medium">Extraction complete</span>
          </div>
        ) : status === 'error' ? (
          <div className="flex items-center gap-2 text-red-400">
            <span className="text-lg">✕</span>
            <span className="font-medium">{error ?? 'Extraction failed'}</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-indigo-400">
            <span className="animate-spin text-lg">⟳</span>
            <span className="font-medium">Extracting…</span>
          </div>
        )}
        {retryCount > 0 && (
          <span className="ml-auto text-xs bg-amber-950 text-amber-400 border border-amber-800 rounded-full px-2.5 py-0.5">
            {retryCount} retr{retryCount === 1 ? 'y' : 'ies'}
          </span>
        )}
      </div>

      {/* Node stepper */}
      <div className="space-y-2">
        {NODES.map((node, i) => {
          const done = completedNodes.has(node.id)
          const active = isActiveNode(node.id)
          const pending = !done && !active

          return (
            <div
              key={node.id}
              className={`flex items-center gap-3 rounded-lg px-4 py-3 transition-all
                ${done ? 'bg-emerald-950/40 border border-emerald-900' :
                  active ? 'bg-indigo-950/40 border border-indigo-800 animate-pulse' :
                  'bg-zinc-900 border border-zinc-800'}`}
            >
              {/* Step number / icon */}
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0
                  ${done ? 'bg-emerald-600 text-white' :
                    active ? 'bg-indigo-600 text-white' :
                    'bg-zinc-800 text-zinc-500'}`}
              >
                {done ? '✓' : i + 1}
              </div>

              {/* Label */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${done ? 'text-emerald-300' : active ? 'text-indigo-300' : 'text-zinc-500'}`}>
                  {node.label}
                </p>
                <p className={`text-xs ${done ? 'text-emerald-600' : active ? 'text-indigo-600' : 'text-zinc-700'}`}>
                  {node.description}
                </p>
              </div>

              {/* Status indicator */}
              <span className="text-xs">
                {done ? <span className="text-emerald-500">done</span> :
                 active ? <span className="text-indigo-400">running</span> :
                 <span className="text-zinc-700">–</span>}
              </span>
            </div>
          )
        })}
      </div>

      {/* Live event log (last 5 messages) */}
      {events.length > 0 && (
        <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-xs text-zinc-600 mb-2 font-mono uppercase tracking-wider">Event log</p>
          <div className="space-y-1 max-h-28 overflow-y-auto">
            {events.slice(-5).map((e, i) => (
              <p key={i} className="text-xs font-mono text-zinc-500">
                <span className="text-zinc-700">{new Date(e.timestamp).toLocaleTimeString()}</span>
                {' · '}
                {e.message}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
