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
import { DEMO_MODELS, type Schema, type ExtractionResult } from './types'

type Step = 'configure' | 'streaming' | 'done'

const HOW_IT_WORKS = [
  {
    n: '01',
    label: 'Configure',
    body: 'Pick a schema, pick a model, optionally bring your own key.',
  },
  {
    n: '02',
    label: 'Extract',
    body: 'The agent streams its reasoning over SSE as it works.',
  },
  {
    n: '03',
    label: 'Validate',
    body: "Output is parsed against your Pydantic schema. Failures trigger a retry, up to three.",
  },
] as const

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [model, setModel] = useState<string>(DEMO_MODELS[0].id)
  const [apiKey, setApiKey] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const [step, setStep] = useState<Step>('configure')
  const [sseUrl, setSseUrl] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [result, setResult] = useState<ExtractionResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const { events, status: sseStatus, error: sseError, reset: resetSSE } = useSSE(sseUrl)

  // Guards against React 19 strict-mode double-invocation of the done effect.
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
      setSseUrl(streamUrl(job.job_id))
      setStep('streaming')
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

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
        <div key="configure" className="step-enter">
          <section className="mb-14">
            <h1 className="font-serif text-[2.5rem] leading-[1.1] tracking-tight text-[var(--color-ink-primary)] mb-5 max-w-[18ch]">
              Self-correcting document extraction.
            </h1>
            <p className="text-[1.0625rem] leading-relaxed text-[var(--color-ink-secondary)] max-w-[60ch]">
              A LangGraph workflow that extracts structured JSON from PDFs, CSVs, and text —
              and retries when the output doesn't match your schema.
            </p>
          </section>

          <section className="mb-14" aria-label="How it works">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-5">
              {HOW_IT_WORKS.map((s, i) => (
                <div key={s.n} className="relative">
                  {i > 0 && (
                    <div
                      aria-hidden="true"
                      className="hidden sm:block absolute -left-3 top-2 bottom-2 w-px bg-[var(--color-hairline)]"
                    />
                  )}
                  <div className="font-mono text-[11px] tracking-[0.14em] text-[var(--color-ember-500)] mb-2">
                    {s.n}
                  </div>
                  <div className="font-serif text-[1.125rem] font-medium text-[var(--color-ink-primary)] mb-1.5">
                    {s.label}
                  </div>
                  <p className="text-sm leading-relaxed text-[var(--color-ink-secondary)]">
                    {s.body}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="card-panel p-7 space-y-7"
          >
            <SchemaSelector value={schema} onChange={setSchema} />
            <ModelSelector value={model} onChange={setModel} />
            <ApiKeyInput value={apiKey} onChange={setApiKey} />
            <DocumentUpload value={file} onChange={setFile} />

            {submitError && (
              <div className="rounded-md border border-[var(--color-rust-500)]/60 bg-[var(--color-rust-500)]/10 px-4 py-3 text-sm text-[var(--color-rust-400)]">
                {submitError}
              </div>
            )}

            <button
              type="submit"
              disabled={!schema || !file || submitting}
              className="group relative w-full py-3.5 px-6 rounded-lg
                         bg-[var(--color-ember-500)] hover:bg-[var(--color-ember-400)]
                         text-[var(--color-ember-ink)] font-medium text-[15px] tracking-tight
                         transition-all duration-150
                         disabled:opacity-40 disabled:cursor-not-allowed
                         hover:enabled:glow-ember-soft active:enabled:scale-[0.99]
                         focus:outline-none focus-visible:enabled:glow-ember"
            >
              {/* Span isolates the pulse to the text — pulsing the button would dim its ember bg. */}
              <span className={submitting ? 'text-pulse' : ''}>
                {submitting ? 'Uploading…' : 'Extract →'}
              </span>
            </button>
          </form>

          <section className="mt-14 pt-6 border-t border-hairline">
            <p className="text-sm leading-relaxed text-[var(--color-ink-tertiary)] max-w-[60ch]">
              Without an API key, requests use a small allowlist of models and are rate-limited
              to ~10 per hour. Pass your own OpenRouter key to bypass both.
            </p>
          </section>
        </div>
      )}

      {step === 'streaming' && (
        <div key="streaming" className="step-enter">
          <div className="flex items-center gap-4 mb-8">
            <button
              onClick={handleReset}
              className="mono-cap text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)] transition-colors duration-150"
            >
              ← back
            </button>
            <h2 className="font-serif text-[1.5rem] font-medium tracking-tight text-[var(--color-ink-primary)]">
              Extracting <span className="font-mono text-[1rem] text-[var(--color-ink-secondary)]">{file?.name}</span>
            </h2>
          </div>
          <ExtractionProgress events={events} status={sseStatus} error={sseError} />
        </div>
      )}

      {step === 'done' && result && (
        <div key="done" className="step-enter">
          <div className="flex items-center justify-between mb-8">
            <h2 className="font-serif text-[1.5rem] font-medium tracking-tight text-[var(--color-ink-primary)]">
              Extraction results
            </h2>
            <button
              onClick={handleReset}
              className="px-4 py-2 rounded-md border border-hairline-strong
                         text-sm text-[var(--color-ink-secondary)]
                         hover:text-[var(--color-ink-primary)] hover:border-[var(--color-ember-500)]/40
                         transition-colors duration-150"
            >
              Extract another
            </button>
          </div>
          <ResultsViewer result={result} />
        </div>
      )}
    </Layout>
  )
}
