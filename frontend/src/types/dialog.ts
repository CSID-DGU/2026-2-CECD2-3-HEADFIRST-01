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

/** 서버에 보내는 이전 턴 기록 (문맥용) */
export type TurnHistoryItem = {
  askedIntent: IntentKey | null
  utterance: string
}

/**
 * POST /api/dialog/turn 요청의 payload (multipart 의 "payload" 필드에 JSON 문자열로 담음)
 * 음성은 같은 요청의 "audio" 필드. text 가 있으면 STT 없이 바로 분류.
 */
export type TurnRequest = {
  sessionId: string
  /** 통화 날짜 YYYY-MM-DD — "그저께" 같은 상대 날짜 계산 기준 */
  callDate: string
  /** 이번에 AI가 물어본 의도 (질문한 의도는 항상 출력되어야 함) */
  askedIntent: IntentKey | null
  /** 지금까지의 대화 (이전 턴 정정 등 문맥 판단용) */
  history: TurnHistoryItem[]
  /** 텍스트 입력 모드일 때 발화 */
  text?: string
}

/** POST /api/dialog/turn 응답 */
export type TurnResponse = {
  /** STT 전사문 (텍스트 입력이면 입력한 문장 그대로) */
  transcript: string
  frames: Frame[]
  /** 사용한 STT 엔진 이름 (선택) */
  sttEngine?: string
  /** 단계별 처리 시간(ms) (선택) */
  latencyMs?: {
    stt?: number
    inference?: number
    total?: number
  }
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
  latencyMs?: TurnResponse['latencyMs']
}
