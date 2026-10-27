// frontend/src/types/api.ts
// 백엔드 API 규격 (backend PR #13 기준, 2026-10-28 Swagger로 확인)

export type SlotName =
  | 'consent'
  | 'name'
  | 'birth_date'
  | 'phone'
  | 'complaint_type'
  | 'occurred_date'
  | 'description'
  | 'reply_channel'

/** consent는 boolean, 나머지는 문자열. 부분값은 '?' 포함 (예: 010-????-7777) */
export type SlotValue = string | boolean | null
export type SlotValues = Record<SlotName, SlotValue>

export type FrameAction = 'inform' | 'uncertain'

export interface Frame {
  slot: SlotName
  action: FrameAction
  /** uncertain이면 null */
  value: SlotValue
}

export interface NextQuestion {
  slot: SlotName
  text: string
}

/* ---------- 공통 응답 ---------- */

export type ErrorCode =
  | 'SESSION_NOT_FOUND' // 404 세션 없음·만료(30분)
  | 'SESSION_DONE' // 409 끝난 대화에 턴 전송
  | 'INVALID_REQUEST' // 422 빈 text 등
  | 'LLM_FAILED' // 502 분류기 오류 (같은 발화 재전송 가능)
  | 'LLM_TIMEOUT' // 504 분류기 시간 초과 (같은 발화 재전송 가능)

export interface ApiSuccess<T> {
  success: true
  message: string
  data: T
}

export interface ApiFailure {
  success: false
  message: string
  data: { errorCode: ErrorCode } | null
}

export type ApiResponse<T> = ApiSuccess<T> | ApiFailure

/* ---------- 세션 ---------- */

/** POST /api/sessions */
export interface SessionSnapshot {
  sessionId: string
  slotOrder: SlotName[]
  slotValues: SlotValues
  /** done이면 null */
  nextQuestion: NextQuestion | null
  done: boolean
}

export interface TurnRecord {
  turnIndex: number
  requestedSlot: SlotName
  transcript: string
  frames: Frame[]
  /** 백엔드에 추가 요청 중. 없으면 프론트에서 requestedSlot으로 문장 생성 */
  question?: string
}

/** GET /api/sessions/{sessionId} */
export interface SessionDetail extends SessionSnapshot {
  turns: TurnRecord[]
}

/* ---------- 턴 ---------- */

export interface TextTurnRequest {
  text: string
}

export interface TimingMs {
  stt: number | null
  llm: number | null
  total: number | null
}

/** POST /api/sessions/{sessionId}/turns/text */
export interface TurnResult {
  turnIndex: number
  requestedSlot: SlotName
  transcript: string
  frames: Frame[]
  slotValues: SlotValues
  nextQuestion: NextQuestion | null
  done: boolean
  /** 텍스트 턴이면 null */
  sttEngine: string | null
  timingMs: TimingMs
}