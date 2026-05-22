import { useEffect, useRef } from 'react'

type TerminalLogProps = {
  lines: string[]
  onToggle?: () => void
  onClearHistory?: () => void
}

export function TerminalLog({ lines, onToggle, onClearHistory }: TerminalLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <section className="rounded-md border border-emerald-400/30 bg-black/45 p-3 shadow-[0_0_22px_rgba(52,211,153,0.1)] transition-all duration-300">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-[11px] tracking-[0.2em] text-emerald-300 uppercase">TERMINAL OUTPUT</p>
          {onClearHistory && (
            <button
              onClick={onClearHistory}
              className="text-[9px] tracking-wider text-rose-400/70 hover:text-rose-300 hover:bg-rose-400/10 transition-colors border border-rose-400/20 px-1.5 py-0.5 rounded font-mono uppercase"
              title="Clear Conversation History"
            >
              Clear
            </button>
          )}
        </div>
        {onToggle && (
          <button
            onClick={onToggle}
            className="text-emerald-400/40 hover:text-emerald-300 transition-colors text-[10px] px-1 hover:bg-emerald-400/10 rounded font-sans"
            title="Hide Terminal"
          >
            ✕
          </button>
        )}
      </div>
      <div className="max-h-40 overflow-y-auto space-y-0.5 pr-1 font-mono text-[11px] text-emerald-300/95">
        {lines.map((line, i) => (
          <p key={i} className="whitespace-pre-wrap leading-relaxed">
            <span className="text-emerald-400/40 mr-1.5">{String(i + 1).padStart(2, '0')}</span>
            {line}
          </p>
        ))}
        <div ref={bottomRef} />
      </div>
    </section>
  )
}
