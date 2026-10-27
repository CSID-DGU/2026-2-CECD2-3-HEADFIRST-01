/**
 * 대화(상담) 단위 데이터 규격 — ontology/ontology.yaml v0.2 기준
 * 백엔드 팀과 확정되면 이 파일만 수정하면 됩니다.
 */

/** 온톨로지의 의도(= AI가 묻는 항목) */
export type IntentKey =
  | 'consent'
  | 'name'
  | 'birth_date'
  | 'phone'
  | 'complaint_type'
  | 'occurred_date'
  | 'description'
  | 'reply_channel'

/**
 * 민원인이 질문에 어떻게 반응했는가
 * - inform    : 질문에 맞는 값을 제공함
 * - uncertain : 응답했으나 값을 하나로 특정할 수 없음 (모름·엉뚱한 답·되물음·답변 거부 등)
 */
export type DialogAction = 'inform' | 'uncertain'

/** inform 이면 형식에 맞는 값(consent 는 boolean), uncertain 이면 null */
export type FrameValue = string | boolean | null

/** 분류기 출력 단위. 발화 하나에 여러 개가 나올 수 있고, 질문한 의도가 맨 앞 */
export type Frame = {
  intent: IntentKey
  action: DialogAction
  value: FrameValue
}

/* ───────────── 화면에서만 쓰는 상태 ───────────── */

/**
 * 항목 하나의 현재 상태
 * - empty     : 아직 정보 없음
 * - filled    : 값 확정
 * - partial   : 값 일부만 확인 (예: 010-????-7777)
 * - uncertain : 물어봤지만 값을 특정하지 못함
 */
export type SlotStatus = 'empty' | 'filled' | 'partial' | 'uncertain'

export type SlotState = {
  status: SlotStatus
  value: FrameValue
  /** 정정되기 전 값들 (오래된 순) */
  previous: { value: FrameValue; turn: number }[]
  /** 마지막으로 바뀐 턴 번호 */
  updatedTurn: number | null
}

export type DialogSlots = Record<IntentKey, SlotState>

/** 한 턴에서 바뀐 항목 */
export type SlotChange = {
  intent: IntentKey
  kind: 'filled' | 'revised' | 'uncertain'
  from: FrameValue
  to: FrameValue
}

/** 대화 한 턴 (AI 질문 + 민원인 응답) */
export type Turn = {
  index: number
  askedIntent: IntentKey | null
  question: string
  input: 'voice' | 'text'
  /** 녹음·업로드한 음성 다시 듣기용 object URL */
  audioUrl?: string
  transcript: string
  frames: Frame[]
  changes: SlotChange[]
  sttEngine?: string
  latencyMs?: {
    stt?: number
    inference?: number
    total?: number
  }
}
