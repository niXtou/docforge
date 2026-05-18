import { useCallback, useRef, useState } from 'react'
import { FieldLabel } from './FieldLabel'

const ACCEPTED = ['.pdf', '.txt', '.csv', '.md']
const ACCEPTED_MIME = ['application/pdf', 'text/plain', 'text/csv', 'text/markdown']

interface Props {
  value: File | null
  onChange: (file: File | null) => void
  disabled?: boolean
}

function isAccepted(file: File): boolean {
  const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase()
  return ACCEPTED.includes(ext) || ACCEPTED_MIME.includes(file.type)
}

export function DocumentUpload({ value, onChange, disabled = false }: Props) {
  const [dragging, setDragging] = useState(false)
  const [formatError, setFormatError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    (file: File) => {
      if (!isAccepted(file)) {
        setFormatError(`Unsupported format. Accepted: ${ACCEPTED.join(', ')}`)
        return
      }
      setFormatError(null)
      onChange(file)
    },
    [onChange],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  return (
    <div className="space-y-2">
      <FieldLabel>Document</FieldLabel>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload document"
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={disabled ? undefined : onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center gap-2 rounded-lg
          py-10 px-6 text-center cursor-pointer transition-all duration-150 select-none
          ${
            disabled
              ? 'opacity-50 cursor-not-allowed border border-hairline border-dashed'
              : dragging
              ? 'border border-[var(--color-ember-500)]/70 bg-[var(--color-ember-500)]/[0.06] glow-ember-soft'
              : value
              ? 'border border-hairline-strong bg-[var(--color-surface-2)]'
              : 'border border-hairline-strong border-dashed bg-[var(--color-surface-2)]/40 hover:bg-[var(--color-surface-2)] hover:border-[var(--color-ember-500)]/30'
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          className="sr-only"
          onChange={onInputChange}
          disabled={disabled}
          aria-hidden="true"
        />

        {value ? (
          <div className="row-enter">
            <p className="font-serif text-[1.05rem] text-[var(--color-ink-primary)] mb-1">
              {value.name}
            </p>
            <p className="mono-cap text-[var(--color-ink-tertiary)]">
              {(value.size / 1024).toFixed(1)} kb · click to change
            </p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onChange(null)
              }}
              className="mt-3 mono-cap text-[var(--color-ink-tertiary)]
                         hover:text-[var(--color-rust-400)] transition-colors duration-150"
            >
              remove
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm text-[var(--color-ink-secondary)]">
              <span className="text-[var(--color-ember-400)]">Click to upload</span>{' '}
              <span className="text-[var(--color-ink-tertiary)]">or drag and drop</span>
            </p>
            <p className="mono-cap text-[var(--color-ink-quaternary)]">
              {ACCEPTED.join(' · ')}
            </p>
          </>
        )}
      </div>

      {formatError && (
        <p className="text-xs text-[var(--color-rust-400)]">{formatError}</p>
      )}
    </div>
  )
}
