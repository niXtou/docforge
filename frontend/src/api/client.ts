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

/**
 * Maximum upload size in megabytes. Mirrors the backend `max_upload_mb` setting
 * (and sits below the Nginx `client_max_body_size`). Used both to pre-validate
 * before uploading and to phrase the 413 message when a layer rejects the file.
 */
export const MAX_UPLOAD_MB = 10

/**
 * FastAPI's HTTPException nests structured details under `detail`, so the body
 * is either `{ detail: "msg" }` or `{ detail: { detail: "msg", code } }`.
 * This normalises both into a flat message + optional code.
 */
function readJsonError(body: ErrorResponse | { detail?: unknown }): { message: string; code?: string } {
  const detail = (body as { detail?: unknown }).detail
  if (detail && typeof detail === 'object') {
    const inner = detail as ErrorResponse
    return { message: inner.detail, code: inner.code ?? undefined }
  }
  if (typeof detail === 'string') {
    return { message: detail, code: (body as ErrorResponse).code ?? undefined }
  }
  return { message: 'Request failed' }
}

/** Friendly fallback for non-JSON errors (e.g. an Nginx 413/502 HTML page). */
function messageForStatus(status: number): string {
  if (status === 413) {
    return `File is too large. The maximum upload size is ${MAX_UPLOAD_MB} MB.`
  }
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status === 502 || status === 503 || status === 504) {
    return 'The server is temporarily unavailable. Please try again shortly.'
  }
  return `Request failed (HTTP ${status}).`
}

/** Throw a descriptive error for non-2xx responses, JSON or not. */
async function checkResponse(res: Response): Promise<void> {
  if (res.ok) return
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    const { message, code } = readJsonError((await res.json()) as ErrorResponse)
    throw Object.assign(new Error(message || messageForStatus(res.status)), { code })
  }
  // Non-JSON body (Nginx error page, gateway timeout, etc.) — map the status.
  throw Object.assign(new Error(messageForStatus(res.status)), {
    code: res.status === 413 ? 'file_too_large' : undefined,
  })
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
