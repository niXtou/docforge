interface LayoutProps {
  children: React.ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-surface-0)]">
      <header className="border-b border-hairline">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center gap-4">
          <a href="/" className="flex items-baseline gap-3 group">
            <span className="font-serif text-[1.35rem] font-medium tracking-tight text-[var(--color-ink-primary)] group-hover:text-[var(--color-ember-200)] transition-colors duration-150">
              DocForge
            </span>
            <span aria-hidden="true" className="w-px h-3.5 bg-[var(--color-hairline-strong)]" />
            <span className="mono-cap text-[var(--color-ink-tertiary)]">
              a self-correcting langgraph workflow
            </span>
          </a>

          <nav className="ml-auto flex items-center gap-6 text-sm">
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-ink-secondary)] hover:text-[var(--color-ink-primary)] transition-colors duration-150"
            >
              API docs
            </a>
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-16">
        {children}
      </main>

      <footer className="border-t border-hairline mt-8">
        <div className="max-w-3xl mx-auto px-6 py-8 mono-cap text-[var(--color-ink-tertiary)] flex items-center justify-between">
          <span>
            built by{' '}
            <a
              href="https://www.nstoug.com"
              className="text-[var(--color-ink-secondary)] hover:text-[var(--color-ember-400)] transition-colors duration-150"
            >
              nstoug
            </a>
          </span>
          <a
            href="https://github.com/niXtou/docforge"
            className="text-[var(--color-ink-secondary)] hover:text-[var(--color-ember-400)] transition-colors duration-150"
          >
            source
          </a>
        </div>
      </footer>
    </div>
  )
}
