import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '../config'

type Bands = { bass: number; mid: number; treble: number }

export function useDubbedAudio() {
  const audioRef  = useRef<HTMLAudioElement | null>(null)
  const urlRef    = useRef<string | null>(null)
  const ctxRef    = useRef<AudioContext | null>(null)
  const frameRef  = useRef<number>(0)
  const activeRef = useRef(true)

  const resolveRef = useRef<(() => void) | null>(null)
  const sessionIdRef = useRef(0)
  const activeSessionIdRef = useRef(0)

  const [isPlaying, setIsPlaying] = useState(false)
  const [amplitude, setAmplitude] = useState(0)
  const [bands, setBands]         = useState<Bands>({ bass: 0, mid: 0, treble: 0 })

  const startSession = useCallback(() => {
    sessionIdRef.current += 1
    activeSessionIdRef.current = sessionIdRef.current
    return sessionIdRef.current
  }, [])

  const cleanupResources = useCallback(() => {
    cancelAnimationFrame(frameRef.current)
    if (resolveRef.current) {
      resolveRef.current()
      resolveRef.current = null
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    if (ctxRef.current) {
      void ctxRef.current.close()
      ctxRef.current = null
    }
    setIsPlaying(false)
    setAmplitude(0)
    setBands({ bass: 0, mid: 0, treble: 0 })
  }, [])

  const stop = useCallback(() => {
    activeSessionIdRef.current = 0
    cleanupResources()
  }, [cleanupResources])

  const playFromApiPath = useCallback(async (apiPath: string, playbackRate = 1, sessionId: number) => {
    cleanupResources()
    if (activeSessionIdRef.current !== sessionId) return false

    const response = await fetch(`${API_BASE}${apiPath}`, { cache: 'no-store' })
    if (activeSessionIdRef.current !== sessionId) return false
    if (!response.ok) throw new Error(`Audio fetch failed: ${response.status}`)

    const blob = await response.blob()
    if (activeSessionIdRef.current !== sessionId) return false
    const url  = URL.createObjectURL(blob)
    urlRef.current = url

    const audio       = new Audio()
    audio.crossOrigin = 'anonymous'
    audio.preload     = 'auto'
    audio.src         = url
    audio.playbackRate = playbackRate
    audioRef.current  = audio

    const ctx = new AudioContext()
    ctxRef.current = ctx
    if (ctx.state === 'suspended') await ctx.resume()
    if (activeSessionIdRef.current !== sessionId) { void ctx.close(); return false }

    const source   = ctx.createMediaElementSource(audio)
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 256
    source.connect(analyser)
    analyser.connect(ctx.destination)

    const data = new Uint8Array(analyser.frequencyBinCount)
    setIsPlaying(true)

    const tick = () => {
      if (activeSessionIdRef.current !== sessionId || !ctxRef.current) return
      analyser.getByteFrequencyData(data)
      let total = 0
      for (let i = 0; i < data.length; i++) total += data[i]
      setAmplitude(total / data.length / 255)
      setBands({
        bass:   bandAvg(data, 0.02, 0.18),
        mid:    bandAvg(data, 0.18, 0.50),
        treble: bandAvg(data, 0.50, 0.98),
      })
      frameRef.current = requestAnimationFrame(tick)
    }
    frameRef.current = requestAnimationFrame(tick)

    await audio.play()
    await new Promise<void>((resolve) => {
      resolveRef.current = resolve
      audio.onended = () => {
        resolveRef.current = null
        resolve()
      }
      audio.onerror = (e) => {
        console.error('[JARVIS audio] playback error:', e)
        resolveRef.current = null
        resolve()
      }
    })

    if (activeSessionIdRef.current !== sessionId) return false

    if (activeRef.current) cleanupResources()
    return true
  }, [cleanupResources])

  useEffect(() => {
    activeRef.current = true
    return () => { activeRef.current = false; stop() }
  }, [stop])

  return { isPlaying, amplitude, bands, playFromApiPath, stop, startSession }
}

function bandAvg(data: Uint8Array, startRatio: number, endRatio: number) {
  const start = Math.floor(data.length * startRatio)
  const end   = Math.max(start + 1, Math.floor(data.length * endRatio))
  let sum = 0
  for (let i = start; i < end; i++) sum += data[i]
  return sum / (end - start) / 255
}
