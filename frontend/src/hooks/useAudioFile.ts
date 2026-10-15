import { useCallback, useEffect, useRef, useState } from 'react'
import { validateAudioFile } from '@/utils/validateAudio'

export type AudioFileState = {
  file: File
  /** <audio src> 에 넣을 임시 URL */
  url: string
  /** 재생 길이(초). 메타데이터를 읽기 전엔 null */
  duration: number | null
}

/**
 * 업로드한 음성 파일 하나를 관리하는 훅
 * - 형식/용량 검사
 * - 미리듣기용 object URL 생성 및 정리
 * - 재생 길이 읽기
 */
export function useAudioFile() {
  const [audio, setAudio] = useState<AudioFileState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  const revoke = () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = null
  }

  const select = useCallback((file: File) => {
    const message = validateAudioFile(file)
    if (message) {
      setError(message)
      return false
    }

    revoke()
    const url = URL.createObjectURL(file)
    urlRef.current = url
    setError(null)
    setAudio({ file, url, duration: null })

    // 재생 길이 읽기
    const el = new Audio()
    el.preload = 'metadata'
    el.onloadedmetadata = () => {
      setAudio((prev) => (prev?.url === url ? { ...prev, duration: el.duration } : prev))
    }
    el.src = url
    return true
  }, [])

  const clear = useCallback(() => {
    revoke()
    setAudio(null)
    setError(null)
  }, [])

  // 컴포넌트가 사라질 때 메모리 정리
  useEffect(() => revoke, [])

  return { audio, error, select, clear, setError }
}
