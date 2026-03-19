import '@testing-library/jest-dom'

// Provide a minimal EventSource mock for jsdom (which does not implement EventSource).
// Tests that need fine-grained control (e.g. useSSE.test.ts) can override this with
// vi.stubGlobal('EventSource', ...) in their own beforeEach.
class NoopEventSource {
  static current: NoopEventSource | null = null
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  close = () => {}
  onerror: ((e: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    NoopEventSource.current = this
  }

  addEventListener(type: string, handler: (e: MessageEvent) => void): void {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(handler)
  }
}

// Install globally so every test environment has EventSource
if (typeof globalThis.EventSource === 'undefined') {
  // @ts-expect-error — jsdom does not define EventSource; we supply a test stub
  globalThis.EventSource = NoopEventSource
}
