import { config } from '@/config'
import { INTENT_MAP } from '@/constants/ontology'
import type { PipelineStage } from '@/types/classify'
import type { Frame, TurnRequest, TurnResponse } from '@/types/dialog'
import { request } from './client'
import { mockSendTurn } from './mockDialog'

/** 한 턴의 민원인 입력 */
export type TurnInput = { kind: 'text'; text: string } | { kind: 'voice'; audio: File }

export type SendTurnOptions = {
  /** 처리 단계가 바뀔 때마다 호출 (진행 표시용) */
  onStage?: (stage: PipelineStage) => void
  signal?: AbortSignal
}

/**
 * 대화 한 턴을 보내고 분류 결과(frames)를 받는다.
 *
 * 실제 API: POST /api/dialog/turn  (multipart/form-data)
 *   - payload : TurnRequest 를 JSON 문자열로
 *   - audio   : 음성 파일 (음성 입력일 때만)
 * VITE_USE_MOCK=false 가 아니면 Mock 응답을 사용한다.
 */
export async function sendTurn(req: TurnRequest, input: TurnInput, options: SendTurnOptions = {}): Promise<TurnResponse> {
  if (config.useMock) {
    return normalizeResponse(await mockSendTurn(req, input, options))
  }

  const { onStage, signal } = options
  const payload: TurnRequest = input.kind === 'text' ? { ...req, text: input.text } : req
  const form = new FormData()
  form.append('payload', JSON.stringify(payload))
  if (input.kind === 'voice') form.append('audio', input.audio)

  onStage?.(input.kind === 'voice' ? 'upload' : 'inference')
  // TODO: 백엔드가 SSE/WebSocket 으로 단계별 진행 상황을 보내주면 여기서 onStage 로 연결
  const res = await request<TurnResponse>('/api/dialog/turn', { method: 'POST', body: form, signal })
  return normalizeResponse(res)
}

/** 서버 응답 방어: 모르는 의도·액션은 버리고, uncertain 의 값은 null 로 맞춘다 */
function normalizeResponse(res: TurnResponse): TurnResponse {
  const frames: Frame[] = (Array.isArray(res.frames) ? res.frames : [])
    .filter((f) => f && f.intent in INTENT_MAP && (f.action === 'inform' || f.action === 'uncertain'))
    .map((f) => ({ intent: f.intent, action: f.action, value: f.action === 'uncertain' ? null : (f.value ?? null) }))
  return { ...res, transcript: res.transcript ?? '', frames }
}
