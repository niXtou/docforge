import { useCallback, useEffect, useRef, useState } from 'react'
import type { StreamEvent } from '../types'

export type SSEStatus = 'idle' | 'connecting' | 'streaming' | 'done' | 'error'

export interface UseSSEResult {
  events: StreamEvent[]
  status: SSEStatus
  error: string | null
  reset: () => void
}

/**
 * Consumes an SSE stream from the given URL.
 *
 * Pass `url = null` to keep the hook dormant. When the URL changes, the
 * previous EventSource is closed and a new one is opened.
 *
 * The EventSource is closed automatically when:
 *   - A `done` event is received (server signals completion)
 *   - An `error` event is received (application-level error from the backend)
 *   - The component unmounts
 */
export function useSSE(url: string | null): UseSSEResult {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [status, setStatus] = useState<SSEStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  // Keep a stable ref to the latest status to avoid stale closure issues in onerror
  const statusRef = useRef<SSEStatus>('idle')

  useEffect(() => {
    if (!url) return

    setStatus('connecting')
    statusRef.current = 'connecting'
    setEvents([])
    setError(null)

    const es = new EventSource(url)

    es.addEventListener('node_completed', (e: MessageEvent) => {
      const event = JSON.parse(e.data as string) as StreamEvent
      setEvents((prev) => [...prev, event])
      setStatus('streaming')
      statusRef.current = 'streaming'
    })

    es.addEventListener('done', (e: MessageEvent) => {
      const event = JSON.parse(e.data as string) as StreamEvent
      setEvents((prev) => [...prev, event])
      setStatus('done')
      statusRef.current = 'done'
      es.close()
    })

    es.addEventListener('error', (e: MessageEvent) => {
      // Application-level error emitted by the backend (has JSON .data)
      if ('data' in e && e.data) {
        const event = JSON.parse(e.data as string) as StreamEvent
        setError(event.message)
      } else {
        setError('Extraction failed')
      }
      setStatus('error')
      statusRef.current = 'error'
      es.close()
    })

    // Network/connection-level error (no data — the browser retries by default;
    // we close here because we do not want silent reconnect loops)
    es.onerror = () => {
      if (statusRef.current !== 'done') {
        setError('Connection lost')
        setStatus('error')
        statusRef.current = 'error'
        es.close()
      }
    }

    return () => es.close()
  }, [url])

  const reset = useCallback(() => {
    setEvents([])
    setStatus('idle')
    statusRef.current = 'idle'
    setError(null)
  }, [])

  return { events, status, error, reset }
}
