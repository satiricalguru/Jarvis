import { useCallback, useEffect, useRef, useState } from 'react'

type SpeechRecognitionCtor = typeof window.SpeechRecognition
type FrequencyBands = {
  bass: number
  mid: number
  treble: number
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | undefined {
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  if (w.SpeechRecognition) return w.SpeechRecognition
  if (w.webkitSpeechRecognition) return w.webkitSpeechRecognition
  return undefined
}

export function useSpeechToText() {
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [resultNonce, setResultNonce] = useState(0)
  const [speechError, setSpeechError] = useState('')
  const [volumeLevel, setVolumeLevel] = useState(0)
  const [frequencyBands, setFrequencyBands] = useState<FrequencyBands>({
    bass: 0,
    mid: 0,
    treble: 0,
  })
  const [speechSupported] = useState(() => {
    if (typeof window === 'undefined') {
      return false
    }
    return Boolean(getSpeechRecognitionCtor())
  })

  // Microphone analysis meter: only runs when isListening is true to protect privacy
  useEffect(() => {
    if (!isListening) {
      const timer = setTimeout(() => {
        setVolumeLevel(0)
        setFrequencyBands({ bass: 0, mid: 0, treble: 0 })
      }, 0)
      return () => clearTimeout(timer)
    }

    let audioContext: AudioContext | null = null
    let analyser: AnalyserNode | null = null
    let dataArray: Uint8Array<ArrayBuffer> | null = null
    let stream: MediaStream | null = null
    let frame = 0

    const bootMicrophoneMeter = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        audioContext = new AudioContext()
        analyser = audioContext.createAnalyser()
        analyser.fftSize = 256

        const source = audioContext.createMediaStreamSource(stream)
        source.connect(analyser)
        dataArray = new Uint8Array(analyser.frequencyBinCount)

        const tick = () => {
          if (!analyser || !dataArray) {
            return
          }
          analyser.getByteFrequencyData(dataArray)
          let total = 0
          for (let i = 0; i < dataArray.length; i += 1) {
            total += dataArray[i]
          }
          const average = total / dataArray.length / 255
          const bass = getBandAverage(dataArray, 0.02, 0.18)
          const mid = getBandAverage(dataArray, 0.18, 0.5)
          const treble = getBandAverage(dataArray, 0.5, 0.98)
          setVolumeLevel(average)
          setFrequencyBands({ bass, mid, treble })
          frame = requestAnimationFrame(tick)
        }

        tick()
      } catch (err) {
        console.error("Microphone analysis initialization failed:", err)
      }
    }

    void bootMicrophoneMeter()

    return () => {
      cancelAnimationFrame(frame)
      stream?.getTracks().forEach((track) => track.stop())
      if (audioContext && audioContext.state !== 'closed') {
        void audioContext.close()
      }
    }
  }, [isListening])

  useEffect(() => {
    const Ctor = getSpeechRecognitionCtor()
    if (!Ctor) {
      return
    }
    const recognition = new Ctor()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'

    recognition.onstart = () => setIsListening(true)
    recognition.onend = () => setIsListening(false)
    recognition.onresult = (event) => {
      const value = event.results[0]?.[0]?.transcript ?? ''
      setTranscript(value)
      setResultNonce((prev) => prev + 1)
    }
    recognition.onerror = (event) => {
      setSpeechError(event.error || 'speech_error')
      setIsListening(false)
    }

    recognitionRef.current = recognition
    return () => recognition.stop()
  }, [])

  const startListening = useCallback(() => {
    try {
      setTranscript('')
      recognitionRef.current?.start()
      setSpeechError('')
    } catch {
      // Ignore invalid-state races when quickly toggling mic.
    }
  }, [])

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  return {
    transcript,
    resultNonce,
    speechError,
    isListening,
    volumeLevel,
    frequencyBands,
    startListening,
    stopListening,
    speechSupported,
  }
}

function getBandAverage(
  array: Uint8Array<ArrayBuffer>,
  startRatio: number,
  endRatio: number,
) {
  const start = Math.floor(array.length * startRatio)
  const end = Math.max(start + 1, Math.floor(array.length * endRatio))
  let sum = 0
  for (let i = start; i < end; i += 1) {
    sum += array[i]
  }
  return sum / (end - start) / 255
}
