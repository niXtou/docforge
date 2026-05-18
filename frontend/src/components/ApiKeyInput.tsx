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
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => handleToggle(!enabled)}
          className={`relative inline-flex h-[18px] w-9 items-center rounded-full transition-colors duration-150
            ${enabled ? 'bg-[var(--color-ember-500)]' : 'bg-[var(--color-surface-3)] border border-hairline-strong'}`}
        >
          <span
            className={`inline-block h-3 w-3 transform rounded-full bg-[var(--color-ink-primary)] transition-transform duration-150
              ${enabled ? 'translate-x-[20px]' : 'translate-x-[3px]'}`}
          />
        </button>
        <label
          className="text-sm text-[var(--color-ink-secondary)] cursor-pointer leading-tight"
          onClick={() => handleToggle(!enabled)}
        >
          Use your own OpenRouter key{' '}
          <span className="text-[var(--color-ink-tertiary)]">— bypasses rate limits</span>
        </label>
      </div>

      {enabled && (
        <div className="relative row-enter">
          <input
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="sk-or-..."
            autoComplete="off"
            className="w-full rounded-md bg-[var(--color-surface-2)] border border-hairline-strong
                       text-[var(--color-ink-primary)] placeholder-[var(--color-ink-quaternary)]
                       px-3.5 py-2.5 pr-14 text-sm font-mono
                       transition-shadow duration-150
                       focus:outline-none focus:glow-ember-soft focus:border-transparent"
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2
                       font-mono text-[11px] uppercase tracking-[0.12em]
                       text-[var(--color-ink-tertiary)] hover:text-[var(--color-ember-400)]
                       transition-colors duration-150"
            aria-label={visible ? 'Hide key' : 'Show key'}
          >
            {visible ? 'hide' : 'show'}
          </button>
        </div>
      )}
    </div>
  )
}
