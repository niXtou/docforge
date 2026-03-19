import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { StreamEvent } from '../types'
import { useSSE } from './useSSE'

// ── Mock EventSource ──────────────────────────────────────────────────────────

type EventHandler = (e: MessageEvent) => void

class MockEventSource {
  static current: MockEventSource | null = null
  listeners: Record<string, EventHandler[]> = {}
  close = vi.fn()
  onerror: ((e: Event) => void) | null = null
  url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.current = this
  }

  addEventListener(type: string, handler: EventHandler): void {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(handler)
  }

  /** Test helper: fire an SSE event with JSON data */
  emit(type: string, payload: StreamEvent): void {
    const event = { data: JSON.stringify(payload) } as MessageEvent
    ;(this.listeners[type] ?? []).forEach((h) => h(event))
  }
}

beforeEach(() => {
  vi.stubGlobal('EventSource', MockEventSource)
})
afterEach(() => {
  vi.unstubAllGlobals()
  MockEventSource.current = null
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useSSE', () => {
  it('starts idle when url is null', () => {
    const { result } = renderHook(() => useSSE(null))
    expect(result.current.status).toBe('idle')
    expect(result.current.events).toHaveLength(0)
  })

  it('moves to connecting when url is set', () => {
    const { result } = renderHook(() => useSSE('/api/extract/job1/stream'))
    expect(result.current.status).toBe('connecting')
  })

  it('appends node_completed events and moves to streaming', () => {
    const { result } = renderHook(() => useSSE('/api/extract/job1/stream'))
    const event: StreamEvent = {
      event: 'node_completed',
      node: 'parse',
      message: "Node 'parse' completed",
      timestamp: '2026-01-01T00:00:00Z',
      data: null,
    }
    act(() => MockEventSource.current!.emit('node_completed', event))
    expect(result.current.status).toBe('streaming')
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0].node).toBe('parse')
  })

  it('moves to done on done event and closes the connection', () => {
    const { result } = renderHook(() => useSSE('/api/extract/job1/stream'))
    const doneEvent: StreamEvent = {
      event: 'done',
      node: null,
      message: 'Extraction complete',
      timestamp: '2026-01-01T00:00:00Z',
      data: { status: 'completed' },
    }
    act(() => MockEventSource.current!.emit('done', doneEvent))
    expect(result.current.status).toBe('done')
    expect(MockEventSource.current!.close).toHaveBeenCalledOnce()
  })

  it('moves to error on error event', () => {
    const { result } = renderHook(() => useSSE('/api/extract/job1/stream'))
    const errEvent: StreamEvent = {
      event: 'error',
      node: null,
      message: 'LLM call failed',
      timestamp: '2026-01-01T00:00:00Z',
      data: null,
    }
    act(() => MockEventSource.current!.emit('error', errEvent))
    expect(result.current.status).toBe('error')
    expect(result.current.error).toBe('LLM call failed')
  })

  it('reset() clears state', () => {
    const { result } = renderHook(() => useSSE('/api/extract/job1/stream'))
    act(() => {
      const event: StreamEvent = {
        event: 'node_completed', node: 'parse', message: '', timestamp: '', data: null,
      }
      MockEventSource.current!.emit('node_completed', event)
    })
    act(() => result.current.reset())
    expect(result.current.events).toHaveLength(0)
    expect(result.current.status).toBe('idle')
  })

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useSSE('/api/extract/job1/stream'))
    const es = MockEventSource.current!
    unmount()
    expect(es.close).toHaveBeenCalledOnce()
  })
})
