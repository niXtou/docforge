import { DEMO_MODELS } from '../types'
import { FieldLabel } from './FieldLabel'

interface Props {
  value: string
  onChange: (model: string) => void
  disabled?: boolean
}

export function ModelSelector({ value, onChange, disabled = false }: Props) {
  return (
    <div className="space-y-2">
      <FieldLabel>Model</FieldLabel>
      <div role="radiogroup" aria-label="Model" className="flex flex-wrap gap-2">
        {DEMO_MODELS.map((m) => {
          const selected = value === m.id
          return (
            <label
              key={m.id}
              className={`
                flex items-center gap-1.5 px-3.5 py-2 rounded-md border text-sm cursor-pointer
                transition-all duration-150 select-none
                ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
                ${
                  selected
                    ? 'border-[var(--color-ember-500)]/60 bg-[var(--color-ember-500)]/10 text-[var(--color-ember-200)]'
                    : 'border-hairline-strong bg-[var(--color-surface-2)] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink-primary)] hover:border-[var(--color-ember-500)]/30'
                }
              `}
            >
              <input
                type="radio"
                name="model"
                value={m.id}
                checked={selected}
                onChange={() => !disabled && onChange(m.id)}
                disabled={disabled}
                className="sr-only"
              />
              {m.label}
            </label>
          )
        })}
      </div>
    </div>
  )
}
