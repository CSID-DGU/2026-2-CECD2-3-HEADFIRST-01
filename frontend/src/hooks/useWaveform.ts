import { useEffect, useState } from 'react'

/**
 * 음성 파일을 디코딩해서 파형(막대 높이 배열, 0~1)을 만든다.
 * 브라우저가 디코딩하지 못하는 형식이면 error 를 돌려준다. (업로드 자체엔 영향 없음)
 */
export function useWaveform(file: File | null, bars = 96) {
  // 어떤 파일의 결과인지 함께 저장 → 파일이 바뀌면 자동으로 '불러오는 중' 상태가 됨
  const [state, setState] = useState<{ file: File; peaks: number[] | null; error: boolean } | null>(null)

  useEffect(() => {
    if (!file) return
    let cancelled = false

    const ctx = new AudioContext()
    file
      .arrayBuffer()
      .then((buf) => ctx.decodeAudioData(buf))
      .then((audioBuffer) => {
        if (!cancelled) setState({ file, peaks: computePeaks(audioBuffer, bars), error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ file, peaks: null, error: true })
      })
      .finally(() => {
        ctx.close().catch(() => {})
      })

    return () => {
      cancelled = true
    }
  }, [file, bars])

  const current = state?.file === file ? state : null
  return { peaks: current?.peaks ?? null, error: current?.error ?? false }
}

function computePeaks(buffer: AudioBuffer, bars: number): number[] {
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i))
  const blockSize = Math.max(1, Math.floor(buffer.length / bars))
  const peaks: number[] = []

  for (let b = 0; b < bars; b++) {
    let max = 0
    const start = b * blockSize
    const end = Math.min(start + blockSize, buffer.length)
    for (const data of channels) {
      // 긴 파일도 빠르게 처리하도록 일부 샘플만 확인
      for (let i = start; i < end; i += 16) {
        const v = Math.abs(data[i])
        if (v > max) max = v
      }
    }
    peaks.push(max)
  }

  const top = Math.max(...peaks, 0.001)
  return peaks.map((p) => p / top)
}
