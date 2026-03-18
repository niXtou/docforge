import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getResult, listSchemas, streamUrl, uploadDocument } from './client'
import type { ExtractionResult, Schema } from '../types'

// Helper to mock a JSON response
function mockFetch(body: unknown, status = 200): void {
  vi.spyOn(global, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('listSchemas', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches and returns schemas', async () => {
    const schemas: Schema[] = [
      { id: 1, name: 'Invoice', description: '', json_schema: {}, is_builtin: true, created_at: '' },
    ]
    mockFetch(schemas)
    const result = await listSchemas()
    expect(result).toEqual(schemas)
    expect(fetch).toHaveBeenCalledWith('/api/schemas')
  })

  it('throws on non-OK response', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('', { status: 500 }),
    )
    await expect(listSchemas()).rejects.toThrow('HTTP 500')
  })
})

describe('uploadDocument', () => {
  afterEach(() => vi.restoreAllMocks())

  it('posts multipart form data and returns job response', async () => {
    const jobResponse = { job_id: 'abc', status: 'pending', schema_name: 'Invoice', created_at: '' }
    mockFetch(jobResponse)

    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    const result = await uploadDocument({
      file,
      schemaId: 1,
      model: 'google/gemini-2.0-flash',
      apiKey: null,
    })

    expect(result).toEqual(jobResponse)
    expect(fetch).toHaveBeenCalledWith('/api/extract', expect.objectContaining({ method: 'POST' }))
  })

  it('throws ErrorResponse on 403', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'not allowed', code: 'model_not_allowed' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const file = new File([''], 'x.txt')
    await expect(
      uploadDocument({ file, schemaId: 1, model: 'openai/gpt-4', apiKey: null }),
    ).rejects.toMatchObject({ code: 'model_not_allowed' })
  })
})

describe('getResult', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches the result by job ID', async () => {
    const result: ExtractionResult = {
      job_id: 'abc',
      status: 'completed',
      data: { invoice_number: 'INV-001' },
      validation_passed: true,
      retries_used: 0,
      model_used: 'google/gemini-2.0-flash',
      processing_time_ms: 1200,
      chunks_processed: 1,
    }
    mockFetch(result)
    expect(await getResult('abc')).toEqual(result)
    expect(fetch).toHaveBeenCalledWith('/api/extract/abc/result')
  })
})

describe('streamUrl', () => {
  it('returns the correct SSE URL', () => {
    expect(streamUrl('my-job-id')).toBe('/api/extract/my-job-id/stream')
  })
})
