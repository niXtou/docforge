import type {
  ErrorResponse,
  ExtractionJobResponse,
  ExtractionResult,
  Schema,
  SchemaCreate,
} from '../types'

/**
 * Base URL for API calls. Empty string means same-origin (Vite proxy in dev,
 * Nginx routing in production). Override with VITE_API_URL for external backends.
 */
const BASE = import.meta.env.VITE_API_URL ?? ''

/** Throw an error for non-2xx responses. Parses JSON error bodies when available. */
async function checkResponse(res: Response): Promise<void> {
  if (res.ok) return
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    const body = (await res.json()) as ErrorResponse
    throw Object.assign(new Error(body.detail), { code: body.code })
  }
  throw new Error(`HTTP ${res.status}`)
}

export async function listSchemas(): Promise<Schema[]> {
  const res = await fetch(`${BASE}/api/schemas`)
  await checkResponse(res)
  return res.json() as Promise<Schema[]>
}

export async function createSchema(payload: SchemaCreate): Promise<Schema> {
  const res = await fetch(`${BASE}/api/schemas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await checkResponse(res)
  return res.json() as Promise<Schema>
}

export interface UploadParams {
  file: File
  schemaId: number
  model: string
  apiKey: string | null
}

export async function uploadDocument(params: UploadParams): Promise<ExtractionJobResponse> {
  const form = new FormData()
  form.append('file', params.file)
  form.append('schema_id', String(params.schemaId))
  form.append('model', params.model)
  if (params.apiKey) form.append('api_key', params.apiKey)

  const res = await fetch(`${BASE}/api/extract`, { method: 'POST', body: form })
  await checkResponse(res)
  return res.json() as Promise<ExtractionJobResponse>
}

export async function getResult(jobId: string): Promise<ExtractionResult> {
  const res = await fetch(`${BASE}/api/extract/${jobId}/result`)
  await checkResponse(res)
  return res.json() as Promise<ExtractionResult>
}

/** Returns the SSE stream URL for a job. Pass to useSSE hook. */
export function streamUrl(jobId: string): string {
  return `${BASE}/api/extract/${jobId}/stream`
}
