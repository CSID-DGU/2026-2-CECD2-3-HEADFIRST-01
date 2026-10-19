import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

export type RecorderStatus =
  | { state: 'idle' }
  | { state: 'requesting' }
  | { state: 'recording' }
  | { state: 'error'; message: string }

type Options = {
  /** 녹음이 끝나면 음성 파일을 넘겨줌 */
  onComplete: (file: File) => void
  /** 최대 녹음 길이(초). 넘으면 자동으로 멈추고 보냄 */
  maxSeconds?: number
}

/** 브라우저마다 지원하는 녹음 형식이 달라서 순서대로 시도 (Safari 는 mp4) */
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
const EXT_BY_MIME: [string, string][] = [
  ['webm', '.webm'],
  ['mp4', '.m4a'],
  ['ogg', '.ogg'],
]
/** 이보다 짧으면 실수로 누른 것으로 보고 버림 */
const MIN_SECONDS = 0.4

export const isRecordingSupported = () =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

function pickMimeType() {
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) ?? ''
}

function toErrorMessage(err: unknown) {
  const name = err instanceof DOMException ? err.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError')
    return '마이크 권한이 거부되었습니다. 주소창의 사이트 설정에서 마이크를 허용해 주세요.'
  if (name === 'NotFoundError') return '연결된 마이크를 찾을 수 없습니다.'
  if (name === 'NotReadableError') return '다른 프로그램이 마이크를 쓰고 있어 녹음할 수 없습니다.'
  return '녹음을 시작하지 못했습니다.'
}

/**
 * 브라우저 마이크 녹음 훅 (MediaRecorder)
 * - start → stop 하면 onComplete 로 File 전달, cancel 하면 버림
 * - 녹음 중 경과 시간(elapsed)과 입력 크기(level, 0~1) 제공
 */
export function useRecorder({ onComplete, maxSeconds = 30 }: Options) {
  const [status, setStatus] = useState<RecorderStatus>({ state: 'idle' })
  const [elapsed, setElapsed] = useState(0)
  const [level, setLevel] = useState(0)

  // 녹음이 끝나는 시점에 항상 최신 콜백을 부르기 위한 사본
  const onCompleteRef = useRef(onComplete)
  useLayoutEffect(() => {
    onCompleteRef.current = onComplete
  })

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const timersRef = useRef<{ interval?: number; raf?: number }>({})
  const discardRef = useRef(false)
  const startedAtRef = useRef(0)

  const cleanup = useCallback(() => {
    const { interval, raf } = timersRef.current
    if (interval) window.clearInterval(interval)
    if (raf) cancelAnimationFrame(raf)
    timersRef.current = {}
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    recorderRef.current = null
    setLevel(0)
  }, [])

  const stop = useCallback(() => {
    const rec = recorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
  }, [])

  const cancel = useCallback(() => {
    discardRef.current = true
    stop()
  }, [stop])

  const start = useCallback(async () => {
    if (recorderRef.current) return
    if (!isRecordingSupported()) {
      setStatus({
        state: 'error',
        message: window.isSecureContext
          ? '이 브라우저는 녹음을 지원하지 않습니다.'
          : '녹음은 HTTPS 또는 localhost 주소에서만 할 수 있습니다.',
      })
      return
    }

    setStatus({ state: 'requesting' })
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      setStatus({ state: 'error', message: toErrorMessage(err) })
      return
    }
    streamRef.current = stream

    const mimeType = pickMimeType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorderRef.current = recorder
    discardRef.current = false
    const chunks: Blob[] = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }
    recorder.onstop = () => {
      const seconds = (performance.now() - startedAtRef.current) / 1000
      const type = recorder.mimeType || mimeType || 'audio/webm'
      cleanup()
      if (discardRef.current) {
        setStatus({ state: 'idle' })
        return
      }
      if (seconds < MIN_SECONDS || chunks.length === 0) {
        setStatus({ state: 'error', message: '녹음이 너무 짧아요. 버튼을 누른 뒤 말하고, 다시 눌러 끝내 주세요.' })
        return
      }
      const ext = EXT_BY_MIME.find(([key]) => type.includes(key))?.[1] ?? '.webm'
      const file = new File(chunks, `recording-${Date.now()}${ext}`, { type: type.split(';')[0] })
      setStatus({ state: 'idle' })
      onCompleteRef.current(file)
    }

    // 입력 크기 측정 (마이크가 실제로 소리를 받는지 눈으로 확인용)
    try {
      const ctx = new AudioContext()
      audioCtxRef.current = ctx
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      ctx.createMediaStreamSource(stream).connect(analyser)
      const buf = new Uint8Array(analyser.fftSize)
      let last = 0
      const tick = (now: number) => {
        if (now - last > 70) {
          analyser.getByteTimeDomainData(buf)
          let sum = 0
          for (const v of buf) sum += ((v - 128) / 128) ** 2
          setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4))
          last = now
        }
        timersRef.current.raf = requestAnimationFrame(tick)
      }
      timersRef.current.raf = requestAnimationFrame(tick)
    } catch {
      /* 레벨 표시는 부가 기능이라 실패해도 녹음은 계속 */
    }

    startedAtRef.current = performance.now()
    setElapsed(0)
    timersRef.current.interval = window.setInterval(() => {
      const s = (performance.now() - startedAtRef.current) / 1000
      setElapsed(s)
      if (s >= maxSeconds) stop()
    }, 200)

    recorder.start()
    setStatus({ state: 'recording' })
  }, [cleanup, maxSeconds, stop])

  const dismissError = useCallback(() => setStatus({ state: 'idle' }), [])

  // 컴포넌트가 사라지면 녹음 중단 + 마이크 해제
  useEffect(
    () => () => {
      discardRef.current = true
      const rec = recorderRef.current
      if (rec && rec.state !== 'inactive') rec.stop()
      cleanup()
    },
    [cleanup],
  )

  return { status, elapsed, level, maxSeconds, start, stop, cancel, dismissError }
}
