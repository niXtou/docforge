import { useState } from 'react'

interface Props {
  value: string
  onChange: (key: string) => void
}

export function ApiKeyInput({ value, onChange }: Props) {
  const [enabled, setEnabled] = useState(false)
  const [visible, setVisible] = useState(false)

  const handleToggle = (checked: boolean) => {
    setEnabled(checked)
    if (!checked) onChange('')
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => handleToggle(!enabled)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors
            ${enabled ? 'bg-indigo-600' : 'bg-zinc-700'}`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
              ${enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'}`}
          />
        </button>
        <label className="text-sm font-medium text-zinc-300 cursor-pointer" onClick={() => handleToggle(!enabled)}>
          Use your own OpenRouter key{' '}
          <span className="text-zinc-500 font-normal">(BYOK — bypasses rate limits)</span>
        </label>
      </div>

      {enabled && (
        <div className="relative">
          <input
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="sk-or-..."
            autoComplete="off"
            className="w-full rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-100
                       placeholder-zinc-600 px-3 py-2 pr-10 text-sm font-mono
                       focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500
                       hover:text-zinc-300 transition-colors text-xs"
            aria-label={visible ? 'Hide key' : 'Show key'}
          >
            {visible ? 'hide' : 'show'}
          </button>
        </div>
      )}
    </div>
  )
}
