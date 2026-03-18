import { useCallback, useRef, useState } from 'react'

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
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-zinc-300">
        Document
      </label>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload document"
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={disabled ? undefined : onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed
          py-10 px-6 text-center cursor-pointer transition-all select-none
          ${disabled ? 'opacity-50 cursor-not-allowed border-zinc-800' :
            dragging ? 'border-indigo-500 bg-indigo-950/30' :
            value ? 'border-zinc-600 bg-zinc-800/50' :
            'border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800/30'}
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
          <>
            <div className="text-2xl">📄</div>
            <p className="font-medium text-zinc-200 text-sm">{value.name}</p>
            <p className="text-xs text-zinc-500">
              {(value.size / 1024).toFixed(1)} KB · Click to change
            </p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onChange(null) }}
              className="mt-1 text-xs text-zinc-500 hover:text-red-400 transition-colors"
            >
              Remove
            </button>
          </>
        ) : (
          <>
            <div className="text-3xl text-zinc-600">⬆</div>
            <p className="text-sm text-zinc-400">
              <span className="text-indigo-400 font-medium">Click to upload</span>
              {' '}or drag and drop
            </p>
            <p className="text-xs text-zinc-600">{ACCEPTED.join(', ')}</p>
          </>
        )}
      </div>

      {formatError && (
        <p className="text-xs text-red-400">{formatError}</p>
      )}
    </div>
  )
}
