import { useEffect, useRef, useState } from 'react'
import { getResult, streamUrl, uploadDocument } from './api/client'
import { useSSE } from './hooks/useSSE'
import { Layout } from './components/Layout'
import { SchemaSelector } from './components/SchemaSelector'
import { ModelSelector } from './components/ModelSelector'
import { ApiKeyInput } from './components/ApiKeyInput'
import { DocumentUpload } from './components/DocumentUpload'
import { ExtractionProgress } from './components/ExtractionProgress'
import { ResultsViewer } from './components/ResultsViewer'
import type { Schema, ExtractionResult } from './types'

type Step = 'configure' | 'streaming' | 'done'

export default function App() {
  // ── Form state ──────────────────────────────────────────────────────────────
  const [schema, setSchema] = useState<Schema | null>(null)
  const [model, setModel] = useState('google/gemini-2.0-flash-001')
  const [apiKey, setApiKey] = useState('')
  const [file, setFile] = useState<File | null>(null)

  // ── Wizard state ────────────────────────────────────────────────────────────
  const [step, setStep] = useState<Step>('configure')
  const [sseUrl, setSseUrl] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [result, setResult] = useState<ExtractionResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // ── SSE hook ────────────────────────────────────────────────────────────────
  const { events, status: sseStatus, error: sseError, reset: resetSSE } = useSSE(sseUrl)

  // When SSE signals done, fetch the final result.
  // useRef guard prevents double-invocation in React 19 strict mode.
  const resultFetchedRef = useRef(false)
  useEffect(() => {
    if (sseStatus === 'done' && step === 'streaming' && jobId && !resultFetchedRef.current) {
      resultFetchedRef.current = true
      getResult(jobId)
        .then((r) => {
          setResult(r)
          setStep('done')
        })
        .catch((e: unknown) => {
          setSubmitError((e as Error).message)
        })
    }
  }, [sseStatus, step, jobId])

  // ── Submit handler ──────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!schema || !file) return

    setSubmitError(null)
    setSubmitting(true)

    try {
      const job = await uploadDocument({
        file,
        schemaId: schema.id,
        model,
        apiKey: apiKey || null,
      })
      setJobId(job.job_id)
      const url = streamUrl(job.job_id)
      setSseUrl(url)
      setStep('streaming')
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  // ── Reset ───────────────────────────────────────────────────────────────────
  const handleReset = () => {
    setStep('configure')
    setFile(null)
    setResult(null)
    setSseUrl(null)
    setJobId(null)
    setSubmitError(null)
    resultFetchedRef.current = false
    resetSSE()
  }

  return (
    <Layout>
      {step === 'configure' && (
        <div className="max-w-2xl mx-auto">
          {/* Hero */}
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold text-zinc-100 mb-3">
              Extract structured data from any document
            </h1>
            <p className="text-zinc-400">
              Upload a PDF, CSV, or text file. DocForge uses a self-correcting LangGraph
              agent to extract structured JSON matching your schema.
            </p>
          </div>

          {/* Form card */}
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-5"
          >
            <SchemaSelector value={schema} onChange={setSchema} />
            <ModelSelector value={model} onChange={setModel} />
            <ApiKeyInput value={apiKey} onChange={setApiKey} />
            <DocumentUpload value={file} onChange={setFile} />

            {submitError && (
              <div className="rounded-lg bg-red-950/50 border border-red-900 px-4 py-3 text-sm text-red-300">
                {submitError}
              </div>
            )}

            <button
              type="submit"
              disabled={!schema || !file || submitting}
              className="w-full py-3 px-6 rounded-xl bg-indigo-600 hover:bg-indigo-500
                         text-white font-semibold text-sm transition-colors
                         disabled:opacity-40 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
                         focus:ring-offset-zinc-900"
            >
              {submitting ? 'Uploading…' : 'Extract →'}
            </button>
          </form>
        </div>
      )}

      {step === 'streaming' && (
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-3 mb-8">
            <button
              onClick={handleReset}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              ← Back
            </button>
            <h2 className="text-xl font-semibold text-zinc-100">
              Extracting from {file?.name}
            </h2>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
            <ExtractionProgress events={events} status={sseStatus} error={sseError} />
          </div>
        </div>
      )}

      {step === 'done' && result && (
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-semibold text-zinc-100">
              Extraction Results
            </h2>
            <button
              onClick={handleReset}
              className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-zinc-700
                         text-sm text-zinc-300 hover:text-zinc-100 transition-colors"
            >
              Extract another
            </button>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
            <ResultsViewer result={result} />
          </div>
        </div>
      )}
    </Layout>
  )
}
