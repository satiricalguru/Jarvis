import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MicBlobScene } from './components/MicBlobScene'
import { SettingsModal, type ProviderChoice } from './components/SettingsModal'
import { TerminalLog } from './components/TerminalLog'
import { useDubbedAudio } from './hooks/useDubbedAudio'
import { useSpeechToText } from './hooks/useSpeechToText'
import { API_BASE } from './config'

function weatherLabel(code?: number) {
  if (code === undefined) return 'Unknown'
  if (code === 0)  return 'Clear'
  if (code <= 3)   return 'Cloudy'
  if (code <= 55)  return 'Drizzle'
  if (code <= 67)  return 'Rain'
  if (code <= 77)  return 'Snow'
  if (code <= 82)  return 'Showers'
  return 'Storm'
}

function dayGreeting(time: Date) {
  const h = time.getHours()
  if (h < 12) return 'Morning'
  if (h < 18) return 'Afternoon'
  return 'Evening'
}

function HudCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-cyan-400/30 bg-black/45 p-3 shadow-[0_0_22px_rgba(34,211,238,0.1)]">
      <p className="mb-2 text-[11px] tracking-[0.2em] text-cyan-300">{title}</p>
      <div className="space-y-1 text-xs text-cyan-100/80">{children}</div>
    </section>
  )
}

function ProviderDot({ label, online }: { label: string; online: boolean }) {
  return (
    <p className="flex items-center gap-2">
      <span className={`inline-block h-2 w-2 rounded-full ${online ? 'bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,0.9)]' : 'bg-rose-400/60'}`} />
      {label}: {online ? 'ONLINE' : 'OFFLINE'}
    </p>
  )
}

function FftChart({ history }: { history: Array<{ b: number; m: number; t: number }> }) {
  const w = 220, h = 54
  const pts = (key: 'b' | 'm' | 't') =>
    history.map((item, i) => {
      const x = (i / Math.max(history.length - 1, 1)) * w
      const y = h - item[key] * h
      return `${x},${Math.max(2, Math.min(h - 2, y))}`
    }).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-[54px] w-full rounded border border-cyan-400/20 bg-black/30">
      <polyline fill="none" stroke="#22d3ee" strokeWidth="1.5" points={pts('b')} />
      <polyline fill="none" stroke="#a78bfa" strokeWidth="1.2" points={pts('m')} />
      <polyline fill="none" stroke="#34d399" strokeWidth="1.2" points={pts('t')} />
    </svg>
  )
}

// Conversation turn type
type Turn = { role: 'user' | 'assistant'; content: string }

// ─── App ─────────────────────────────────────────────────────
function App() {
  const [isSettingsOpen, setIsSettingsOpen]   = useState(false)
  const [isTerminalOpen, setIsTerminalOpen]   = useState(true)
  const [hotkey, setHotkey]                   = useState('Spacebar')
  const [holdToTalk, setHoldToTalk]           = useState(true)
  const [ttsEnabled, setTtsEnabled]           = useState(true)
  const [ttsRate, setTtsRate]                 = useState(1)
  const [playVoicePrefix, setPlayVoicePrefix] = useState(false)
  const [strictCloneMode, setStrictCloneMode] = useState(false)
  const [continuousMode, setContinuousMode]   = useState(true)

  const [selectedProvider, setSelectedProvider] = useState<ProviderChoice>('auto')
  const [selectedModel, setSelectedModel]       = useState('')

  // Full conversation history (sent to backend for context)
  const [history, setHistory] = useState<Turn[]>([])

  const [jarvisReply, setJarvisReply]   = useState('')
  const [activeProvider, setActiveProvider] = useState('')
  const [typedCommand, setTypedCommand] = useState('')
  const [isThinking, setIsThinking]     = useState(false)

  const [time, setTime]                       = useState(() => new Date())
  const [batteryPercent, setBatteryPercent]   = useState<number | null>(null)
  const [weather, setWeather]                 = useState<{ temp?: number; label?: string }>({})
  const [locationName, setLocationName]       = useState('Ranchi')
  const [locationSub, setLocationSub]         = useState('Jharkhand, India')
  const [providerHealth, setProviderHealth]   = useState({ groq: false, mistral: false, openrouter: false, ollama: false })
  const [fftHistory, setFftHistory]           = useState<Array<{ b: number; m: number; t: number }>>([])

  const [ttsEngine, setTtsEngine]           = useState('unknown')
  const [ttsStatus, setTtsStatus]           = useState('idle')
  const [ttsMode, setTtsMode]               = useState('...')
  const [pendingAudioUrl, setPendingAudioUrl] = useState<string | null>(null)

  const dubbedAudio  = useDubbedAudio()
  const sendLockRef  = useRef(false)

  // Stable ref for continuousMode so the resultNonce effect never captures stale state
  const continuousModeRef = useRef(continuousMode)
  useEffect(() => { continuousModeRef.current = continuousMode }, [continuousMode])

  const { transcript, resultNonce, speechError, isListening, volumeLevel,
    frequencyBands, startListening, stopListening, speechSupported } = useSpeechToText()

  // Clock
  useEffect(() => {
    const t = window.setInterval(() => setTime(new Date()), 1000)
    return () => window.clearInterval(t)
  }, [])

  // Battery
  useEffect(() => {
    const nav = navigator as Navigator & { getBattery?: () => Promise<{ level: number }> }
    if (!nav.getBattery) return
    nav.getBattery().then((b) => setBatteryPercent(Math.round(b.level * 100))).catch(() => {})
  }, [])


  // Weather & location
  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      try {
        const r = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${coords.latitude}&longitude=${coords.longitude}&current=temperature_2m,weather_code`)
        if (r.ok) {
          const d = await r.json()
          setWeather({ temp: d?.current?.temperature_2m, label: weatherLabel(d?.current?.weather_code) })
        }
      } catch { /* silent */ }
      try {
        const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${coords.latitude}&lon=${coords.longitude}`, {
          headers: { 'User-Agent': 'JarvisAI-Assistant/1.0' }
        })
        if (r.ok) {
          const d = await r.json()
          const address = d.address
          if (address) {
            const city  = address.city || address.town || address.village || address.suburb || address.county || ''
            const state = address.state || ''
            const country = address.country || ''
            if (city) { setLocationName(city); setLocationSub([state, country].filter(Boolean).join(', ')) }
            else if (state) { setLocationName(state); setLocationSub(country) }
          }
        }
      } catch { /* silent */ }
    })
  }, [])

  // Provider health + TTS mode polling
  useEffect(() => {
    const refresh = async () => {
      try {
        const r = await fetch(`${API_BASE}/health/providers`)
        if (r.ok) {
          const d = await r.json()
          setProviderHealth({ groq: Boolean(d.groq), mistral: Boolean(d.mistral), openrouter: Boolean(d.openrouter), ollama: Boolean(d.ollama) })
        }
      } catch {
        setProviderHealth({ groq: false, mistral: false, openrouter: false, ollama: false })
      }
      try {
        const r = await fetch(`${API_BASE}/tts/mode`)
        if (r.ok) { const d = await r.json(); setTtsMode(d.active_mode ?? '...') }
      } catch { /* silent */ }
    }
    void refresh()
    const t = window.setInterval(refresh, 20000)
    return () => window.clearInterval(t)
  }, [])

  // FFT history
  useEffect(() => {
    const t = window.setInterval(() => {
      setFftHistory((prev) => [...prev, { b: frequencyBands.bass, m: frequencyBands.mid, t: frequencyBands.treble }].slice(-40))
    }, 350)
    return () => window.clearInterval(t)
  }, [frequencyBands])

  // ── sendMessage — stable reference via useCallback ────────────────────────
  const sendMessage = useCallback(async (message: string) => {
    if (sendLockRef.current) return
    sendLockRef.current = true
    setIsThinking(true)
    dubbedAudio.stop()
    const userTurn: Turn = { role: 'user', content: message }
    setHistory((prev) => [...prev, userTurn])
    try {
      const body: Record<string, unknown> = {
        message,
        history: history.slice(-20),  // send last 20 turns
      }
      if (selectedProvider !== 'auto') body.provider = selectedProvider
      if (selectedModel) body.model = selectedModel

      const r = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        setJarvisReply('JARVIS: Backend offline, Sir.')
        setActiveProvider('offline')
        return
      }
      const data = await r.json()
      const reply = data.reply ?? ''
      setJarvisReply(reply)
      setActiveProvider(data.provider ?? '')
      setHistory((prev) => [...prev, { role: 'assistant', content: reply }])

      if (data.audio_url) {
        setTtsEngine(data.tts_provider ?? 'unknown')
        setPendingAudioUrl(data.audio_url)
        setTtsStatus(`queued: ${data.tts_provider ?? '?'} @ ${data.audio_url}`)
      } else {
        setTtsEngine('none')
        setTtsStatus('no audio from backend')
      }
    } catch {
      setJarvisReply('JARVIS: Network issue detected, Sir.')
      setActiveProvider('offline')
    } finally {
      sendLockRef.current = false
      setIsThinking(false)
    }
  }, [history, selectedProvider, selectedModel, dubbedAudio])


  // Stop audio immediately when user starts speaking
  useEffect(() => {
    if (isListening) {
      dubbedAudio.stop()
    }
  }, [isListening, dubbedAudio])

  // Voice transcript → send
  // Uses continuousModeRef (not continuousMode state) to avoid stale closure
  // that would silently drop mic restarts when the effect captures an old value.
  useEffect(() => {
    if (!transcript.trim()) return
    void sendMessage(transcript)
    if (continuousModeRef.current) {
      setTimeout(() => startListening(), 800)
    }
  }, [resultNonce]) // eslint-disable-line react-hooks/exhaustive-deps

  // TTS playback
  useEffect(() => {
    if (!ttsEnabled || !pendingAudioUrl) return
    if (strictCloneMode && ttsEngine !== 'pocket-tts') {
      setTtsStatus(`strict clone: blocked ${ttsEngine} — only pocket-tts allowed`)
      setPendingAudioUrl(null)
      return
    }
    setTtsStatus(`playing via ${ttsEngine} [${ttsMode}]`)

    const runPlayback = async () => {
      const sessionId = dubbedAudio.startSession()
      try {
        if (playVoicePrefix) {
          const ok = await dubbedAudio.playFromApiPath('/tts/prefix', 1, sessionId)
          if (!ok) return
        }
        await dubbedAudio.playFromApiPath(pendingAudioUrl, ttsRate, sessionId)
        setTtsStatus(`done via ${ttsEngine}`)
      } catch (e: unknown) {
        console.error('[JARVIS] audio play error:', e)
        setTtsStatus('playback error — check console')
      } finally {
        setPendingAudioUrl(null)
      }
    }
    void runPlayback()
  }, [ttsEnabled, pendingAudioUrl, ttsEngine, ttsMode, strictCloneMode, playVoicePrefix, ttsRate, dubbedAudio])

  // Configurable Hotkey Listener (supports combos like Meta+J, or single keys like Spacebar / Space)
  const hotkeyPressedRef = useRef(false)
  useEffect(() => {
    const norm = hotkey.toLowerCase()
    const key  = norm.split('+').pop()
    if (!key) return

    const isSpaceKey = key === 'space' || key === 'spacebar'

    const onDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return
      if ((norm.includes('meta') || norm.includes('cmd')) && !e.metaKey) return

      const keyMatched = isSpaceKey
        ? (e.key === ' ' || e.code === 'Space')
        : (e.key.toLowerCase() === key)

      if (!keyMatched) return
      e.preventDefault()
      if (e.repeat) return

      hotkeyPressedRef.current = true
      if (holdToTalk) {
        dubbedAudio.stop()
        startListening()
      } else {
        if (isListening) {
          stopListening()
        } else {
          dubbedAudio.stop()
          startListening()
        }
      }
    }

    const onUp = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return

      const keyMatched = isSpaceKey
        ? (e.key === ' ' || e.code === 'Space')
        : (e.key.toLowerCase() === key)

      if (!keyMatched) return
      e.preventDefault()

      if (hotkeyPressedRef.current) {
        hotkeyPressedRef.current = false
        if (holdToTalk) stopListening()
      }
    }

    const onBlur = () => {
      if (hotkeyPressedRef.current) {
        hotkeyPressedRef.current = false
        if (holdToTalk) stopListening()
      }
    }

    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [hotkey, holdToTalk, isListening, startListening, stopListening, dubbedAudio])


  const logs = useMemo(() => [
    `JARVIS CORE: Voice ${speechSupported ? 'online' : 'unsupported'}`,
    `INPUT: ${holdToTalk ? 'Hold-To-Talk' : 'Toggle'} · HOTKEY: ${hotkey}`,
    isListening ? 'STATUS: Listening, Sir...' : isThinking ? 'STATUS: Processing...' : 'STATUS: Standing by, Sir.',
    speechError ? `STT ERR: ${speechError}` : 'STT: no error',
    `FFT: B${frequencyBands.bass.toFixed(2)} M${frequencyBands.mid.toFixed(2)} T${frequencyBands.treble.toFixed(2)}`,
    transcript ? `USER: ${transcript}` : 'USER: Awaiting command...',
    jarvisReply ? `JARVIS: ${jarvisReply.slice(0, 80)}` : 'JARVIS: Ready to assist, Sir.',
    activeProvider ? `LLM: ${activeProvider}${selectedModel ? ' / ' + selectedModel : ''}` : 'LLM: Pending...',
    `TTS ENGINE: ${ttsEngine} · MODE: ${ttsMode}`,
    `TTS STATUS: ${ttsStatus}`,
    `HISTORY: ${history.length} turns`,
  ], [speechSupported, holdToTalk, hotkey, isListening, isThinking, frequencyBands, speechError,
      transcript, jarvisReply, activeProvider, selectedModel, ttsEngine, ttsMode, ttsStatus, history])

  const visualVolume = dubbedAudio.isPlaying ? dubbedAudio.amplitude : volumeLevel
  const visualBands  = dubbedAudio.isPlaying ? dubbedAudio.bands     : frequencyBands

  return (
    <main className="relative min-h-screen overflow-hidden bg-black text-cyan-100">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(14,116,144,0.14),transparent_55%),linear-gradient(rgba(20,184,166,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(20,184,166,0.08)_1px,transparent_1px)] bg-[length:100%_100%,50px_50px,50px_50px]" />

      <section className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1500px] flex-col px-4 py-4">
        {/* ── Header ── */}
        <header className="mb-4 flex items-center justify-between rounded-md border border-cyan-400/30 bg-black/40 px-4 py-2 shadow-[0_0_30px_rgba(34,211,238,0.12)]">
          <div className="flex items-center gap-3">
            <p className="text-lg tracking-[0.25em] text-cyan-300">J.A.R.V.I.S.</p>
            {activeProvider && activeProvider !== 'offline' && (
              <span className="rounded-sm border border-cyan-400/25 bg-cyan-400/10 px-2 py-0.5 text-[10px] tracking-widest text-cyan-400">
                {activeProvider.toUpperCase()}{selectedModel ? ` · ${selectedModel.split('/').pop()}` : ''}
              </span>
            )}
            {ttsMode !== 'catalog:marius' && ttsMode !== '...' && (
              <span className={`rounded-sm border px-2 py-0.5 text-[10px] tracking-widest ${ttsMode.startsWith('voice-cloning') ? 'border-white/30 text-white' : ttsMode.startsWith('catalog') ? 'border-cyan-400/30 text-cyan-400/70' : 'border-white/10 text-white/20'}`}>
                🎙 {ttsMode}
              </span>
            )}
            {isThinking && (
              <span className="animate-pulse rounded-sm border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[10px] tracking-widest text-amber-300">
                ⚡ PROCESSING
              </span>
            )}
          </div>
          <nav className="flex gap-6 text-xs tracking-[0.2em] text-cyan-100/85">
            <button onClick={() => window.scrollTo(0, 0)} className="hover:text-cyan-300 transition-colors">HOME</button>
            <button onClick={() => setIsTerminalOpen((prev) => !prev)} className={`${isTerminalOpen ? 'text-emerald-400 hover:text-emerald-300' : 'hover:text-cyan-300'} transition-colors`}>TERMINAL</button>
            <button onClick={() => setIsSettingsOpen(true)} className="hover:text-cyan-300 transition-colors">SETTINGS</button>
            <button onClick={() => { setHistory([]); setJarvisReply('') }} className="hover:text-rose-300 transition-colors" title="Clear conversation">RESET</button>
          </nav>
        </header>


        <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_300px]">
          {/* ── Left sidebar ── */}
          <aside className="space-y-4">
            <HudCard title="LOCATION">
              <p className="text-base text-cyan-300">{locationName}</p>
              <p className="mt-1 text-xs text-cyan-100/70">{locationSub}</p>
            </HudCard>
            <HudCard title="SYSTEM STATUS">
              <p>Battery: {batteryPercent !== null ? `${batteryPercent}%` : 'n/a'}</p>
              <p>Mic: {speechSupported ? 'ONLINE' : 'UNSUPPORTED'}</p>
              <p>Channel: {activeProvider || 'Standby'}</p>
              <p>Mode: {selectedProvider === 'auto' ? 'AUTO' : selectedProvider.toUpperCase()}</p>
              <p>Assistant: {isListening ? 'LISTENING' : isThinking ? 'THINKING' : 'IDLE'}</p>
              <p>History: {history.length} turns</p>
              <div className="mt-1 space-y-1 border-t border-cyan-400/10 pt-1">
                <ProviderDot label="GROQ"       online={providerHealth.groq} />
                <ProviderDot label="MISTRAL"    online={providerHealth.mistral} />
                <ProviderDot label="OPENROUTER" online={providerHealth.openrouter} />
                <ProviderDot label="OLLAMA"     online={providerHealth.ollama} />
              </div>
            </HudCard>
            <HudCard title="ACTIVITY">
              <div className="space-y-1 text-[11px]">
                {logs.slice(0, 6).map((line, i) => <p key={i} className="text-cyan-100/80">{line}</p>)}
              </div>
            </HudCard>
            {isTerminalOpen && (
              <TerminalLog
                lines={logs}
                onToggle={() => setIsTerminalOpen(false)}
                onClearHistory={() => { setHistory([]); setJarvisReply('') }}
              />
            )}
          </aside>

          {/* ── Main orb panel ── */}
          <section className="relative rounded-md border border-cyan-400/25 bg-black/30 p-2">
            <div className="h-[58vh] min-h-[360px] w-full">
              <MicBlobScene volumeLevel={visualVolume} frequencyBands={visualBands} />
            </div>

            {/* Reply / thinking overlay */}
            <div className="absolute bottom-24 left-1/2 w-[min(92%,480px)] -translate-x-1/2 rounded-md border border-cyan-400/35 bg-black/55 px-5 py-3 text-center shadow-[0_0_24px_rgba(34,211,238,0.2)]">
              <p className="text-2xl text-cyan-300">Good {dayGreeting(time)}, Sir</p>
              {isThinking ? (
                <p className="mt-1 animate-pulse text-xs text-amber-300/80">Processing your request…</p>
              ) : (
                <p className="mt-1 text-xs text-cyan-100/75 line-clamp-3">{jarvisReply || 'At your service, Sir.'}</p>
              )}
            </div>

            {/* Command input */}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const cmd = typedCommand.trim()
                if (!cmd || isThinking) return
                void sendMessage(cmd)
                setTypedCommand('')
              }}
              className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[min(92%,440px)] flex items-center gap-2 rounded-md border border-emerald-300/30 bg-black/65 px-3 py-2"
            >
              <div className="flex-1">
                <label className="mb-0.5 block text-[10px] tracking-[0.16em] text-emerald-300">COMMAND INPUT</label>
                <input
                  value={typedCommand}
                  onChange={(e) => setTypedCommand(e.target.value)}
                  disabled={isThinking}
                  className="w-full bg-transparent text-sm text-emerald-200 outline-none placeholder:text-emerald-200/40 disabled:opacity-40"
                  placeholder="> Sir, type your command..."
                />
              </div>
              <button
                type="submit"
                disabled={!typedCommand.trim() || isThinking}
                className="flex-shrink-0 rounded border border-emerald-400/40 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-400/20 transition-colors disabled:opacity-30"
              >
                {isThinking ? '…' : '⏎'}
              </button>
            </form>
          </section>


          {/* ── Right sidebar ── */}
          <aside className="space-y-4">
            <HudCard title="TIME & WEATHER">
              <p className="text-xl text-cyan-300">{time.toLocaleTimeString()}</p>
              <p>{time.toLocaleDateString()}</p>
              <p>{weather.temp !== undefined ? `${Math.round(weather.temp)}°C` : '—'} {weather.label ?? ''}</p>
            </HudCard>
            <HudCard title="VOICE CONTROL">
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (isListening) {
                      stopListening()
                    } else {
                      dubbedAudio.stop()
                      startListening()
                    }
                  }}
                  disabled={isThinking}
                  className={`rounded border px-3 py-1 text-xs transition-colors disabled:opacity-40 ${isListening ? 'border-rose-400/50 bg-rose-400/10 text-rose-300 hover:bg-rose-400/20' : 'border-cyan-400/40 bg-cyan-400/10 hover:bg-cyan-400/20'}`}
                >
                  {isListening ? '■ STOP' : '● START'}
                </button>
                <button onClick={() => setIsSettingsOpen(true)} className="rounded border border-fuchsia-400/40 bg-fuchsia-400/10 px-3 py-1 text-xs hover:bg-fuchsia-400/20">
                  SETTINGS
                </button>
              </div>
              <p className="mt-2 text-[11px]">Hotkey: {hotkey}</p>
              <p className="text-[11px]">Mode: {holdToTalk ? 'Hold-to-Talk' : 'Toggle'}</p>
              <p className="text-[11px]">Voice: {ttsEnabled ? `ON (${ttsRate.toFixed(1)}×)` : 'OFF'}</p>
              <p className="text-[11px]">Continuous: {continuousMode ? 'ON' : 'OFF'}</p>
              <p className="text-[11px] text-cyan-100/50">LLM: {selectedProvider === 'auto' ? 'Auto' : selectedProvider.toUpperCase()}</p>
              <p className={`text-[11px] ${ttsMode.startsWith('voice-cloning') ? '' : 'text-cyan-100/50'}`}>
                Voice-cloning: {ttsMode.startsWith('voice-cloning') ? 'ON' : 'OFF'}
              </p>
            </HudCard>
            <HudCard title="MICROPHONE FFT">
              <p>Bass:   {(frequencyBands.bass   * 100).toFixed(0)}%</p>
              <p>Mid:    {(frequencyBands.mid    * 100).toFixed(0)}%</p>
              <p>Treble: {(frequencyBands.treble * 100).toFixed(0)}%</p>
              <FftChart history={fftHistory} />
            </HudCard>

            {/* Conversation history preview */}
            {history.length > 0 && (
              <HudCard title="RECENT EXCHANGE">
                <div className="max-h-32 space-y-1 overflow-y-auto text-[11px]">
                  {history.slice(-4).map((turn, i) => (
                    <p key={i} className={turn.role === 'user' ? 'text-emerald-300/80' : 'text-cyan-100/70'}>
                      <span className="text-[9px] tracking-widest opacity-60">{turn.role.toUpperCase()} › </span>
                      {turn.content.slice(0, 60)}{turn.content.length > 60 ? '…' : ''}
                    </p>
                  ))}
                </div>
              </HudCard>
            )}
          </aside>
        </div>
      </section>

      <SettingsModal
        isOpen={isSettingsOpen}
        hotkey={hotkey} holdToTalk={holdToTalk} ttsEnabled={ttsEnabled}
        ttsRate={ttsRate} playVoicePrefix={playVoicePrefix}
        strictCloneMode={strictCloneMode}
        continuousMode={continuousMode}
        selectedProvider={selectedProvider} selectedModel={selectedModel}
        providerHealth={providerHealth}
        onClose={() => setIsSettingsOpen(false)}
        onHotkeyChange={setHotkey} onHoldToTalkChange={setHoldToTalk}
        onTtsEnabledChange={setTtsEnabled} onTtsRateChange={setTtsRate}
        onPlayVoicePrefixChange={setPlayVoicePrefix}
        onStrictCloneModeChange={setStrictCloneMode}
        onContinuousModeChange={setContinuousMode}
        onProviderChange={setSelectedProvider} onModelChange={setSelectedModel}
      />
    </main>
  )
}

export default App
