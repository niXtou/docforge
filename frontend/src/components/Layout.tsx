interface LayoutProps {
  children: React.ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-sm">
            D
          </div>
          <div>
            <span className="font-semibold text-zinc-100">DocForge</span>
            <span className="ml-2 text-xs text-zinc-500 font-mono">AI Document Intelligence</span>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              API Docs
            </a>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-10">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800 py-6">
        <div className="max-w-5xl mx-auto px-4 text-center text-sm text-zinc-600">
          Built by{' '}
          <a
            href="https://www.nstoug.com"
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            nstoug
          </a> and AI
          {' · '}
          <a
            href="https://github.com/niXtou/docforge"
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  )
}
