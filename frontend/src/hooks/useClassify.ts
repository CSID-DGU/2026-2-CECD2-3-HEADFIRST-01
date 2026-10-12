import { useCallback, useEffect, useRef, useState } from 'react'
import { classifyAudio } from '@/api/classify'
import type { ClassifyStatus, PipelineStage } from '@/types/classify'

/**
 * 분류 요청 상태 관리 훅
 * idle → running(단계별) → success | error
 */
export function useClassify() {
  const [status, setStatus] = useState<ClassifyStatus>({ state: 'idle' })
  const controllerRef = useRef<AbortController | null>(null)

  const run = useCallback(async (file: File) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    let lastStage: PipelineStage = 'upload'
    setStatus({ state: 'running', stage: lastStage })
    try {
      const result = await classifyAudio(file, {
        signal: controller.signal,
        onStage: (stage) => {
          lastStage = stage
          setStatus({ state: 'running', stage })
        },
      })
      setStatus({ state: 'success', result })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.'
      setStatus({ state: 'error', message, stage: lastStage })
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [])

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setStatus({ state: 'idle' })
  }, [])

  const reset = cancel

  // 페이지를 떠나면 진행 중인 요청 취소
  useEffect(() => () => controllerRef.current?.abort(), [])

  return { status, run, cancel, reset }
}
