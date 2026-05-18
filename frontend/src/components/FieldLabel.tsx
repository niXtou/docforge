interface Props {
  htmlFor?: string
  children: React.ReactNode
}

export function FieldLabel({ htmlFor, children }: Props) {
  return (
    <label
      htmlFor={htmlFor}
      className="block mono-cap text-[var(--color-ink-tertiary)]"
    >
      {children}
    </label>
  )
}
