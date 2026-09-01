import { useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { createSchema } from '../api/client'
import { highlightJson } from '../lib/highlightJson'
import type { Schema, SchemaCreate } from '../types'

interface Props {
  onClose: () => void
  onCreated: (schema: Schema) => void
}

// Document type → the schema's x-doc-type extension key, which selects the
// extraction playbook on the backend. "generic" omits the key entirely.
const DOC_TYPES = [
  { id: 'generic', label: 'Generic' },
  { id: 'invoice', label: 'Invoice' },
  { id: 'resume', label: 'Resume / CV' },
  { id: 'research_paper', label: 'Research paper' },
] as const
type DocType = (typeof DOC_TYPES)[number]['id']

const FIELD_TYPES = [
  { id: 'string', label: 'string' },
  { id: 'number', label: 'number' },
  { id: 'integer', label: 'integer' },
  { id: 'boolean', label: 'boolean' },
  { id: 'string[]', label: 'string array' },
] as const
type FieldType = (typeof FIELD_TYPES)[number]['id']

interface FieldDraft {
  id: number
  name: string
  type: FieldType
  description: string
  required: boolean
}

const FIELD_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/

let nextFieldId = 1
function newField(): FieldDraft {
  return { id: nextFieldId++, name: '', type: 'string', description: '', required: false }
}

function propertyFor(field: FieldDraft): Record<string, unknown> {
  const base: Record<string, unknown> =
    field.type === 'string[]'
      ? { type: 'array', items: { type: 'string' } }
      : { type: field.type }
  if (field.description.trim()) base.description = field.description.trim()
  return base
}

/** Build the JSON Schema from the named fields. Blank-name rows are ignored. */
function buildJsonSchema(fields: FieldDraft[], docType: DocType): Record<string, unknown> {
  const named = fields.filter((f) => f.name.trim())
  const schema: Record<string, unknown> = { type: 'object' }
  if (docType !== 'generic') schema['x-doc-type'] = docType
  schema.properties = Object.fromEntries(named.map((f) => [f.name.trim(), propertyFor(f)]))
  const required = named.filter((f) => f.required).map((f) => f.name.trim())
  if (required.length > 0) schema.required = required
  return schema
}

/** Client-side check mirroring what the backend would reject with a 422. */
function validateFields(fields: FieldDraft[]): string | null {
  const names = fields.map((f) => f.name.trim()).filter(Boolean)
  const bad = names.find((n) => !FIELD_NAME.test(n))
  if (bad) {
    return `Field name "${bad}" is invalid — use letters, digits and underscores, not starting with a digit.`
  }
  const dupe = names.find((n, i) => names.indexOf(n) !== i)
  if (dupe) return `Field name "${dupe}" is used more than once.`
  return null
}

const INPUT =
  'w-full rounded-md bg-[var(--color-surface-2)] border border-hairline-strong ' +
  'text-[var(--color-ink-primary)] placeholder-[var(--color-ink-quaternary)] ' +
  'px-3 py-2 text-sm transition-shadow duration-150 ' +
  'focus:outline-none focus:glow-ember-soft focus:border-transparent'

const SELECT = `${INPUT} appearance-none cursor-pointer pr-8`

export function SchemaBuilder({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [docType, setDocType] = useState<DocType>('generic')
  const [fields, setFields] = useState<FieldDraft[]>(() => [newField()])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const jsonSchema = useMemo(() => buildJsonSchema(fields, docType), [fields, docType])
  const preview = useMemo(() => highlightJson(JSON.stringify(jsonSchema, null, 2)), [jsonSchema])

  const hasNamedField = fields.some((f) => f.name.trim())
  const canSubmit = name.trim().length > 0 && hasNamedField && !submitting

  const updateField = (id: number, patch: Partial<FieldDraft>) =>
    setFields((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)))
  const removeField = (id: number) => setFields((prev) => prev.filter((f) => f.id !== id))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const fieldError = validateFields(fields)
    if (fieldError) {
      setError(fieldError)
      return
    }
    setError(null)
    setSubmitting(true)
    const payload: SchemaCreate = {
      name: name.trim(),
      description: description.trim(),
      json_schema: jsonSchema,
    }
    try {
      const created = await createSchema(payload)
      onCreated(created)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-label="New schema"
        onSubmit={(e) => void handleSubmit(e)}
        onClick={(e) => e.stopPropagation()}
        className="card-panel max-w-3xl w-full max-h-[90vh] flex flex-col"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-hairline">
          <h3 className="font-serif text-[1.05rem] font-medium text-[var(--color-ink-primary)]">
            New schema
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] transition-colors duration-150 text-sm"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="px-5 py-4 space-y-5 overflow-y-auto">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-3">
            <label className="space-y-1.5">
              <span className="block mono-cap text-[var(--color-ink-tertiary)]">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Purchase order"
                maxLength={100}
                className={INPUT}
              />
            </label>
            <label className="space-y-1.5">
              <span className="block mono-cap text-[var(--color-ink-tertiary)]">Description</span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this schema extracts"
                className={INPUT}
              />
            </label>
            <label className="space-y-1.5">
              <span className="block mono-cap text-[var(--color-ink-tertiary)]">Document type</span>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value as DocType)}
                className={SELECT}
              >
                {DOC_TYPES.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="mono-cap text-[var(--color-ink-tertiary)]">Fields</span>
              <button
                type="button"
                onClick={() => setFields((prev) => [...prev, newField()])}
                className="mono-cap text-[var(--color-ember-400)] hover:text-[var(--color-ember-200)] transition-colors duration-150"
              >
                + add field
              </button>
            </div>

            <div className="space-y-2">
              {fields.map((f, i) => (
                <div
                  key={f.id}
                  className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.9fr)_minmax(0,1.6fr)_auto_auto] gap-2 items-center row-enter"
                >
                  <input
                    aria-label={`Field ${i + 1} name`}
                    value={f.name}
                    onChange={(e) => updateField(f.id, { name: e.target.value })}
                    placeholder="field_name"
                    spellCheck={false}
                    className={`${INPUT} font-mono`}
                  />
                  <select
                    aria-label={`Field ${i + 1} type`}
                    value={f.type}
                    onChange={(e) => updateField(f.id, { type: e.target.value as FieldType })}
                    className={SELECT}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  <input
                    aria-label={`Field ${i + 1} description`}
                    value={f.description}
                    onChange={(e) => updateField(f.id, { description: e.target.value })}
                    placeholder="What to extract, and where to find it"
                    className={INPUT}
                  />
                  <label className="flex items-center gap-1.5 mono-cap-sm text-[var(--color-ink-tertiary)] cursor-pointer select-none px-1">
                    <input
                      type="checkbox"
                      aria-label={`Field ${i + 1} required`}
                      checked={f.required}
                      onChange={(e) => updateField(f.id, { required: e.target.checked })}
                      className="accent-[var(--color-ember-500)]"
                    />
                    req
                  </label>
                  <button
                    type="button"
                    onClick={() => removeField(f.id)}
                    aria-label={`Remove field ${i + 1}`}
                    className="mono-cap text-[var(--color-ink-tertiary)] hover:text-[var(--color-rust-400)] transition-colors duration-150 px-1"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <p className="text-xs text-[var(--color-ink-tertiary)] leading-relaxed">
              Field names: letters, digits and underscores, not starting with a digit. The description
              is the instruction the model follows — say what to extract and where it lives.
            </p>
          </div>

          <div className="space-y-1.5">
            <span className="block mono-cap text-[var(--color-ink-tertiary)]">JSON Schema preview</span>
            <pre
              data-testid="schema-preview"
              className="rounded-md bg-[var(--color-surface-0)] border border-hairline px-4 py-3 text-[12px] font-mono
                         text-[var(--color-ink-secondary)] overflow-auto max-h-56 leading-[1.7]"
            >
              {preview}
            </pre>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-md border border-[var(--color-rust-500)]/60 bg-[var(--color-rust-500)]/10 px-4 py-3 text-sm text-[var(--color-rust-400)]"
            >
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-hairline">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-md border border-hairline-strong text-sm
                       text-[var(--color-ink-secondary)] hover:text-[var(--color-ink-primary)]
                       transition-colors duration-150"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="px-5 py-2 rounded-md bg-[var(--color-ember-500)] hover:bg-[var(--color-ember-400)]
                       text-[var(--color-ember-ink)] text-sm font-medium transition-colors duration-150
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  )
}
