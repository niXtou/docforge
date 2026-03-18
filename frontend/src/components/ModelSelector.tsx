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
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-100
                   px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500
                   focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {DEMO_MODELS.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  )
}
