import { DEMO_MODELS } from '../types'

interface Props {
  value: string
  onChange: (model: string) => void
  disabled?: boolean
}

export function ModelSelector({ value, onChange, disabled = false }: Props) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-zinc-300">
        Model
      </label>
      <div
        role="radiogroup"
        aria-label="Model"
        className="flex flex-wrap gap-2"
      >
        {DEMO_MODELS.map((m) => (
          <label
            key={m.id}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm cursor-pointer
              transition-colors select-none
              ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
              ${value === m.id
                ? 'bg-indigo-600 border-indigo-500 text-white'
                : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-zinc-600 hover:text-zinc-100'}
            `}
          >
            <input
              type="radio"
              name="model"
              value={m.id}
              checked={value === m.id}
              onChange={() => !disabled && onChange(m.id)}
              disabled={disabled}
              className="sr-only"
            />
            {m.label}
          </label>
        ))}
      </div>
    </div>
  )
}
