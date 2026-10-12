import { config } from '@/config'
import type { ClassifyResponse, PipelineStage } from '@/types/classify'
import { request } from './client'
import { mockClassify } from './mock'

export type ClassifyOptions = {
  /** 처리 단계가 바뀔 때마다 호출 (진행 표시용) */
  onStage?: (stage: PipelineStage) => void
  /** 요청 취소용 */
  signal?: AbortSignal
}

/**
 * 음성 파일을 보내 의도·엔티티 분류 결과를 받아온다.
 *
 * 실제 API: POST /api/classify  (multipart/form-data, 필드명 "audio")
 * VITE_USE_MOCK=false 가 아니면 Mock 응답을 사용한다.
 */
export async function classifyAudio(file: File, options: ClassifyOptions = {}): Promise<ClassifyResponse> {
  if (config.useMock) {
    return mockClassify(file, options)
  }

  const { onStage, signal } = options
  const form = new FormData()
  form.append('audio', file)

  onStage?.('upload')
  // TODO: 백엔드가 SSE/WebSocket 으로 단계별 진행 상황을 보내주면 여기서 onStage 로 연결
  const promise = request<ClassifyResponse>('/api/classify', { method: 'POST', body: form, signal })
  onStage?.('stt')
  return promise
}
