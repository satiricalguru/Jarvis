import { useEffect, useState } from 'react'
import { API_BASE } from '../config'

type ModelInfo = { id: string; name: string; free: boolean }

type ProviderHealth = {
  groq: boolean
  mistral: boolean
  openrouter: boolean
  ollama: boolean
}

export type ProviderChoice = 'auto' | 'groq' | 'mistral' | 'openrouter' | 'ollama'

export type SettingsModalProps = {
  isOpen: boolean
  hotkey: string
  holdToTalk: boolean
  ttsEnabled: boolean
  ttsRate: number
  playVoicePrefix: boolean
  strictCloneMode: boolean
  continuousMode: boolean
  selectedProvider: ProviderChoice
  selectedModel: string
  providerHealth: ProviderHealth
  onClose: () => void
  onHotkeyChange: (v: string) => void
  onHoldToTalkChange: (v: boolean) => void
  onTtsEnabledChange: (v: boolean) => void
  onTtsRateChange: (v: number) => void
  onPlayVoicePrefixChange: (v: boolean) => void
  onStrictCloneModeChange: (v: boolean) => void
  onContinuousModeChange: (v: boolean) => void
  onProviderChange: (v: ProviderChoice) => void
  onModelChange: (v: string) => void
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <p className="mb-2 text-[10px] tracking-[0.2em] text-cyan-400/80 uppercase">{title}</p>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

// ── Fixed toggle: color map now correctly produces Tailwind class strings ──
const TOGGLE_COLORS = {
  cyan:    { track: 'bg-cyan-400',    border: 'border-cyan-400/25' },
  fuchsia: { track: 'bg-fuchsia-400', border: 'border-fuchsia-400/25' },
  emerald: { track: 'bg-emerald-400', border: 'border-emerald-400/25' },
  yellow:  { track: 'bg-yellow-400',  border: 'border-yellow-400/25' },
  amber:   { track: 'bg-amber-400',   border: 'border-amber-400/25' },
} as const

type ToggleColor = keyof typeof TOGGLE_COLORS

function ToggleRow({
  label,
  checked,
  onChange,
  color = 'cyan',
  hint,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  color?: ToggleColor
  hint?: string
}) {
  const { track, border } = TOGGLE_COLORS[color]
  return (
    <div>
      <label
        className={`flex cursor-pointer items-center justify-between rounded-md border ${border} bg-black/30 px-3 py-2.5 text-sm select-none`}
      >
        <span className="text-cyan-100/80">{label}</span>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          onClick={() => onChange(!checked)}
          className={`relative h-5 w-9 rounded-full transition-colors duration-200 ${checked ? track : 'bg-white/10'}`}
        >
          <span
            className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ${checked ? 'translate-x-4' : 'translate-x-0'}`}
          />
        </button>
      </label>
      {hint && <p className="mt-1 px-1 text-[10px] text-cyan-100/40">{hint}</p>}
    </div>
  )
}

const PROVIDERS: { id: ProviderChoice; label: string }[] = [
  { id: 'auto',       label: 'AUTO' },
  { id: 'groq',       label: 'GROQ' },
  { id: 'mistral',    label: 'MISTRAL' },
  { id: 'openrouter', label: 'OPENROUTER' },
  { id: 'ollama',     label: 'OLLAMA' },
]

function ProviderPill({ id, label, selected, online, onClick }: {
  id: ProviderChoice; label: string; selected: boolean; online?: boolean; onClick: () => void
}) {
  const isAuto = id === 'auto'
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[11px] tracking-widest transition-all ${
        selected
          ? 'border-cyan-400/70 bg-cyan-400/15 text-cyan-300 shadow-[0_0_14px_rgba(34,211,238,0.25)]'
          : 'border-white/10 bg-white/5 text-cyan-100/50 hover:border-cyan-400/30 hover:text-cyan-100/80'
      }`}
    >
      {!isAuto && (
        <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-emerald-400 shadow-[0_0_6px_rgba(74,222,128,0.9)]' : 'bg-rose-400/70'}`} />
      )}
      {label}
    </button>
  )
}

export function SettingsModal({
  isOpen, hotkey, holdToTalk, ttsEnabled, ttsRate, playVoicePrefix,
  strictCloneMode, continuousMode, selectedProvider, selectedModel, providerHealth,
  onClose, onHotkeyChange, onHoldToTalkChange, onTtsEnabledChange, onTtsRateChange,
  onPlayVoicePrefixChange, onStrictCloneModeChange, onContinuousModeChange,
  onProviderChange, onModelChange,
}: SettingsModalProps) {
  const [models, setModels]           = useState<ModelInfo[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [freeOnly, setFreeOnly]       = useState(false)
  const [tab, setTab]                 = useState<'general' | 'provider' | 'keys'>('general')

  const [keys, setKeys]           = useState({ groq: '', mistral: '', openrouter: '', huggingface: '' })
  const [keysStatus, setKeysStatus] = useState({ groq: false, mistral: false, openrouter: false, huggingface: false })
  const [keysSaved, setKeysSaved] = useState(false)

  useEffect(() => {
    if (tab !== 'keys') return
    let active = true
    fetch(`${API_BASE}/settings/keys/status`)
      .then((r) => r.json())
      .then((status) => { if (active) setKeysStatus(status) })
      .catch(() => {})
    return () => { active = false }
  }, [tab])

  useEffect(() => {
    let active = true
    if (selectedProvider === 'auto') {
      Promise.resolve().then(() => {
        if (active) setModels([])
      })
      return
    }
    Promise.resolve().then(() => {
      if (active) setLoadingModels(true)
    })
    fetch(`${API_BASE}/models/${selectedProvider}`)
      .then((r) => r.json())
      .then((data) => { if (active) setModels(data.models ?? []) })
      .catch(() => { if (active) setModels([]) })
      .finally(() => { if (active) setLoadingModels(false) })
    return () => { active = false }
  }, [selectedProvider])

  useEffect(() => {
    onModelChange('')
  }, [selectedProvider]) // eslint-disable-line react-hooks/exhaustive-deps

  const visibleModels = freeOnly ? models.filter((m) => m.free) : models

  async function saveKeys() {
    const body = {
      groq:        keys.groq        || null,
      mistral:     keys.mistral     || null,
      openrouter:  keys.openrouter  || null,
      huggingface: keys.huggingface || null,
    }
    try {
      await fetch(`${API_BASE}/settings/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setKeysSaved(true)
      setKeys({ groq: '', mistral: '', openrouter: '', huggingface: '' })
      const res = await fetch(`${API_BASE}/settings/keys/status`)
      setKeysStatus(await res.json())
      setTimeout(() => setKeysSaved(false), 2500)
    } catch { /* silent */ }
  }

  if (!isOpen) return null

  const tabCls = (t: string) =>
    `px-4 py-1.5 text-[11px] tracking-[0.15em] rounded-t-md transition-colors ${
      tab === t
        ? 'bg-cyan-400/15 text-cyan-300 border border-b-0 border-cyan-400/30'
        : 'text-cyan-100/40 hover:text-cyan-100/70'
    }`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="relative w-full max-w-lg rounded-xl border border-cyan-400/30 bg-[#03060a] text-cyan-100 shadow-[0_0_60px_rgba(34,211,238,0.15)]">
        <div className="flex items-center justify-between border-b border-cyan-400/15 px-6 py-4">
          <h2 className="text-sm tracking-[0.25em] text-cyan-300">J.A.R.V.I.S. SETTINGS</h2>
          <button onClick={onClose} className="text-cyan-100/40 hover:text-cyan-300 text-lg leading-none">✕</button>
        </div>

        <div className="flex gap-1 px-6 pt-3">
          <button className={tabCls('general')}  onClick={() => setTab('general')}>GENERAL</button>
          <button className={tabCls('provider')} onClick={() => setTab('provider')}>PROVIDER</button>
          <button className={tabCls('keys')}     onClick={() => setTab('keys')}>API KEYS</button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 pb-6">

          {/* ── GENERAL ── */}
          {tab === 'general' && (
            <>
              <Section title="Input">
                <label className="block text-xs text-cyan-100/60">
                  Hotkey combination
                  <input
                    value={hotkey}
                    onChange={(e) => onHotkeyChange(e.target.value)}
                    className="mt-1.5 w-full rounded-md border border-cyan-400/25 bg-black/40 px-3 py-2 text-sm text-cyan-100 outline-none focus:border-cyan-400/60 transition-colors"
                    placeholder="Spacebar"
                  />
                </label>
                <ToggleRow label="Hold-to-talk mode" checked={holdToTalk} onChange={onHoldToTalkChange} color="fuchsia" />
              </Section>

              <Section title="Voice Output">
                <ToggleRow label="Enable voice output" checked={ttsEnabled} onChange={onTtsEnabledChange} color="emerald" />
                <ToggleRow
                  label="Continuous listening (auto-restart mic)"
                  checked={continuousMode}
                  onChange={onContinuousModeChange}
                  color="amber"
                  hint="After each reply, mic restarts automatically so you can keep talking."
                />
                <label className="block text-xs text-cyan-100/60">
                  Speed: {ttsRate.toFixed(1)}×
                  <input
                    type="range" min={0.7} max={1.3} step={0.1}
                    value={ttsRate}
                    onChange={(e) => onTtsRateChange(Number(e.target.value))}
                    className="mt-1.5 w-full accent-cyan-400"
                  />
                </label>
                <ToggleRow label="Play custom voice prefix each reply" checked={playVoicePrefix} onChange={onPlayVoicePrefixChange} color="yellow" />
                <ToggleRow
                  label="Strict Clone Mode (Pocket-TTS only)"
                  checked={strictCloneMode}
                  onChange={onStrictCloneModeChange}
                  color="fuchsia"
                  hint={strictCloneMode ? '⚠ Blocks gtts/huggingface fallback. Disable if you hear no voice.' : undefined}
                />
              </Section>
            </>
          )}

          {/* ── PROVIDER ── */}
          {tab === 'provider' && (
            <>
              <Section title="Select Provider">
                <div className="flex flex-wrap gap-2">
                  {PROVIDERS.map(({ id, label }) => (
                    <ProviderPill
                      key={id} id={id} label={label}
                      selected={selectedProvider === id}
                      online={id !== 'auto' ? providerHealth[id as keyof ProviderHealth] : undefined}
                      onClick={() => onProviderChange(id)}
                    />
                  ))}
                </div>
                {selectedProvider === 'auto' && (
                  <p className="mt-2 text-[11px] text-cyan-100/45">
                    Auto mode tries Groq → Mistral → OpenRouter → Ollama in order.
                  </p>
                )}
              </Section>

              {selectedProvider !== 'auto' && (
                <Section title="Select Model">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] text-cyan-100/50">
                      {loadingModels ? 'Loading...' : `${visibleModels.length} model${visibleModels.length !== 1 ? 's' : ''}`}
                    </p>
                    <label className="flex items-center gap-2 text-[11px] text-cyan-100/60 cursor-pointer select-none">
                      <span>Free only</span>
                      <button
                        type="button" role="switch" aria-checked={freeOnly}
                        onClick={() => setFreeOnly((v) => !v)}
                        className={`relative h-4 w-8 rounded-full transition-colors duration-200 ${freeOnly ? 'bg-emerald-400' : 'bg-white/10'}`}
                      >
                        <span className={`absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform duration-200 ${freeOnly ? 'translate-x-4' : 'translate-x-0'}`} />
                      </button>
                    </label>
                  </div>

                  <button
                    type="button"
                    onClick={() => onModelChange('')}
                    className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-all ${
                      !selectedModel
                        ? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-300'
                        : 'border-white/10 bg-white/5 text-cyan-100/40 hover:border-cyan-400/20 hover:text-cyan-100/70'
                    }`}
                  >
                    ⚡ Use provider default
                  </button>

                  <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
                    {loadingModels ? (
                      <div className="py-4 text-center text-[11px] text-cyan-100/30 animate-pulse">Fetching models…</div>
                    ) : visibleModels.length === 0 ? (
                      <div className="py-4 text-center text-[11px] text-cyan-100/30">
                        {selectedProvider === 'ollama' ? 'No local Ollama models found. Is Ollama running?' : 'No models available.'}
                      </div>
                    ) : (
                      visibleModels.map((m) => (
                        <button
                          key={m.id} type="button"
                          onClick={() => onModelChange(m.id)}
                          className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-xs transition-all ${
                            selectedModel === m.id
                              ? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-300'
                              : 'border-white/10 bg-white/5 text-cyan-100/60 hover:border-cyan-400/20 hover:text-cyan-100/90'
                          }`}
                        >
                          <span>{m.name}</span>
                          {m.free && (
                            <span className="rounded-sm bg-emerald-400/15 px-1.5 py-0.5 text-[9px] tracking-wider text-emerald-400">FREE</span>
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </Section>
              )}
            </>
          )}

          {/* ── API KEYS ── */}
          {tab === 'keys' && (
            <Section title="Provider API Keys">
              <p className="text-[11px] text-cyan-100/40">
                Keys are saved to the backend .env configuration file on disk.
              </p>
              {(
                [
                  { field: 'groq',        label: 'Groq API Key',       placeholder: 'gsk_…' },
                  { field: 'mistral',     label: 'Mistral API Key',    placeholder: 'sk-…'  },
                  { field: 'openrouter',  label: 'OpenRouter API Key', placeholder: 'sk-or-…' },
                  { field: 'huggingface', label: 'HuggingFace Token',  placeholder: 'hf_…'  },
                ] as const
              ).map(({ field, label, placeholder }) => (
                <label key={field} className="block text-xs text-cyan-100/60">
                  <div className="mb-1 flex items-center justify-between">
                    <span>{label}</span>
                    <span className={`text-[10px] ${keysStatus[field] ? 'text-emerald-400' : 'text-rose-400/70'}`}>
                      {keysStatus[field] ? '● SET' : '○ NOT SET'}
                    </span>
                  </div>
                  <input
                    type="password"
                    value={keys[field]}
                    onChange={(e) => setKeys((prev) => ({ ...prev, [field]: e.target.value }))}
                    className="w-full rounded-md border border-cyan-400/20 bg-black/40 px-3 py-2 text-sm text-cyan-100 outline-none focus:border-cyan-400/50 transition-colors"
                    placeholder={placeholder}
                    autoComplete="off"
                  />
                </label>
              ))}
              <button
                type="button" onClick={saveKeys}
                className="mt-2 w-full rounded-md border border-cyan-400/40 bg-cyan-400/10 py-2 text-xs tracking-widest text-cyan-300 hover:bg-cyan-400/20 transition-colors"
              >
                {keysSaved ? '✓ SAVED' : 'SAVE KEYS'}
              </button>
            </Section>
          )}
        </div>

        <div className="flex items-center justify-end border-t border-cyan-400/10 px-6 py-3">
          <button
            onClick={onClose}
            className="rounded-md border border-cyan-400/30 bg-cyan-400/8 px-5 py-1.5 text-xs tracking-widest text-cyan-300 hover:bg-cyan-400/15 transition-colors"
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  )
}
