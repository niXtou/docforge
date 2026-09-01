// Mirrors backend Pydantic response models (app/models/schemas.py).
// Keep in sync with the backend — field names and types must match exactly.

export interface Schema {
  id: number
  name: string
  description: string
  json_schema: Record<string, unknown>
  is_builtin: boolean
  created_at: string
}

export interface ExtractionJobResponse {
  job_id: string
  /** always "pending" at creation time */
  status: string
  schema_name: string
  created_at: string
}

/** One row of GET /api/extract — a listing, never the extracted data itself */
export interface ExtractionJobSummary {
  job_id: string
  status: string
  schema_name: string
  original_filename: string
  model_used: string
  created_at: string
  completed_at: string | null
  processing_time_ms: number | null
  retries_used: number
  /** null until the workflow has run */
  validation_passed: boolean | null
}

/** Where an extracted value was verified against the document */
export interface FieldEvidence {
  /** Snippet of the document the value was verified against; empty when unverified */
  quote: string
  /** verbatim = found in the text; judge = LLM judge; unverified = not checkable */
  method: 'verbatim' | 'judge' | 'unverified'
  /** false only for values the judge rejected (nulled / dropped from data) */
  supported: boolean
}

export interface ExtractionResult {
  job_id: string
  status: 'completed' | 'completed_with_errors' | 'failed'
  /** The extracted fields; null if the job failed before producing output */
  data: Record<string, unknown> | null
  validation_passed: boolean
  retries_used: number
  model_used: string
  processing_time_ms: number
  chunks_processed: number
  /** Human-readable failure reason; populated when status === 'failed' */
  error_message: string | null
  /** Errors from the final validation pass; empty when validation passed */
  validation_errors: string[]
  /**
   * Per-field provenance keyed by field name, or "field[i]" for array items
   * (i = position in data). Judge-rejected array items sit under
   * "field[dropped:<original i>]".
   */
  evidence: Record<string, FieldEvidence>
}

/** Payload for POST /api/schemas */
export interface SchemaCreate {
  name: string
  description: string
  json_schema: Record<string, unknown>
}

/**
 * SSE event emitted by GET /api/extract/{job_id}/stream.
 * The `event` field matches the SSE `event:` line type.
 *
 * `data` per event:
 *   node_completed — keys_updated, plus chunk/extract: chunks; verify_grounding:
 *                    issues, evidence_count; validate: errors, attempt
 *   retry          — attempt, errors (validation failed; extraction re-runs)
 *   progress       — node, completed, total
 */
export interface StreamEvent {
  event: 'node_completed' | 'progress' | 'retry' | 'error' | 'done'
  node: string | null
  message: string
  timestamp: string
  data: Record<string, unknown> | null
}

/** Standard error body from the backend (403, 413, 429 responses) */
export interface ErrorResponse {
  detail: string
  code: 'rate_limit_exceeded' | 'model_not_allowed' | 'file_too_large' | null
}

/**
 * Demo-allowed model options shown in the UI.
 * Must stay in sync with backend settings.demo_allowed_models.
 */
export const DEMO_MODELS = [
  { id: 'google/gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash Lite' },
  { id: 'openai/gpt-5.4-nano', label: 'GPT-5.4 Nano' },
  { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
] as const
