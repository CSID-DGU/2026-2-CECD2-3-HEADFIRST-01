import { config } from '@/config'
import { INTENT_MAP } from '@/constants/ontology'
import type { PipelineStage } from '@/types/classify'
import type { Frame, SessionDetail, SessionSnapshot, TurnResult } from '@/types/api'
import { ApiError, apiRequest, jsonBody } from './client'
import * as mock from './mockSession'

/** 한 턴의 민원인 입력 */
export type TurnInput = { kind: 'text'; text: string } | { kind: 'voice'; audio: File }

export type RequestOptions = { signal?: AbortSignal }

export type SendTurnOptions = RequestOptions & {
  /** 처리 단계가 바뀔 때마다 호출 (진행 표시용) */
  onStage?: (stage: PipelineStage) => void
}

/** 음성 턴은 서버 미구현. API 모드에서는 텍스트 입력만 */
export const supportsVoice = config.useMock

const sessionPath = (id: string) => `/api/sessions/${encodeURIComponent(id)}`

/** 대화 시작: POST /api/sessions */
export async function createSession(opts: RequestOptions = {}): Promise<SessionSnapshot> {
  if (config.useMock) return mock.createSession(opts)
  return apiRequest<SessionSnapshot>('/api/sessions', { method: 'POST', signal: opts.signal })
}

/** 대화 상태 조회: GET /api/sessions/{sessionId} */
export async function getSession(sessionId: string, opts: RequestOptions = {}): Promise<SessionDetail> {
  const res = config.useMock
    ? await mock.getSession(sessionId, opts)
    : await apiRequest<SessionDetail>(sessionPath(sessionId), { signal: opts.signal })
  return {
    ...res,
    turns: (Array.isArray(res.turns) ? res.turns : []).map((t) => ({ ...t, frames: normalizeFrames(t.frames) })),
  }
}

/** 텍스트 턴: POST /api/sessions/{sessionId}/turns/text */
export async function sendTurn(
  sessionId: string,
  input: TurnInput,
  options: SendTurnOptions = {},
): Promise<TurnResult> {
  if (config.useMock) return normalizeTurn(await mock.sendTurn(sessionId, input, options))

  if (input.kind === 'voice') {
    throw new ApiError('음성 입력은 아직 서버에서 지원하지 않습니다. 텍스트로 입력해주세요.', undefined, 'INVALID_REQUEST')
  }

  options.onStage?.('inference')
  // TODO: 음성 턴 POST /api/sessions/{sessionId}/turns 구현되면 여기서 분기
  const res = await apiRequest<TurnResult>(
    `${sessionPath(sessionId)}/turns/text`,
    jsonBody({ text: input.text }, { signal: options.signal }),
  )
  return normalizeTurn(res)
}

/* ---------- 응답 방어 ---------- */

function isFrame(f: unknown): f is Frame {
  if (typeof f !== 'object' || f === null) return false
  const { slot, action } = f as { slot?: unknown; action?: unknown }
  return typeof slot === 'string' && slot in INTENT_MAP && (action === 'inform' || action === 'uncertain')
}

/** 모르는 슬롯·액션은 버리고 uncertain 값은 null로 맞춘다 */
function normalizeFrames(frames: unknown): Frame[] {
  if (!Array.isArray(frames)) return []
  return frames
    .filter(isFrame)
    .map((f) => ({ slot: f.slot, action: f.action, value: f.action === 'uncertain' ? null : (f.value ?? null) }))
}

function normalizeTurn(res: TurnResult): TurnResult {
  return { ...res, transcript: res.transcript ?? '', frames: normalizeFrames(res.frames) }
}