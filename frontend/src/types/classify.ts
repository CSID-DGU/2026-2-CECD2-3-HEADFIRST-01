/**
 * 백엔드와 주고받는 데이터 규격 (API 명세 초안)
 * 백엔드 팀과 확정되면 이 파일만 수정하면 됩니다.
 */

/** 추출된 엔티티 하나 */
export type Entity = {
  /** 엔티티 종류 (예: "역명", "날짜", "물품") */
  type: string
  /** 발화에서 뽑힌 값 (예: "강남역") */
  value: string
  /** 정제된 발화(normalizedText) 안에서의 시작/끝 위치 (선택) */
  start?: number
  end?: number
}

/** 분류된 의도 */
export type Intent = {
  /** 의도 라벨 (예: "분실물_문의") */
  label: string
  /** 0 ~ 1 사이 확신도 */
  confidence: number
}

/** POST /api/classify 응답 */
export type ClassifyResponse = {
  requestId: string
  /** STT가 변환한 원문 (노이즈 포함) */
  transcript: string
  /** 발화 노이즈(간투사·반복 등)를 제거한 문장 (선택) */
  normalizedText?: string
  intent: Intent
  /** 확신도 순 상위 후보 (선택) */
  candidates?: Intent[]
  entities: Entity[]
  /** 단계별 처리 시간(ms) (선택) */
  latencyMs?: {
    stt?: number
    inference?: number
    total?: number
  }
}

/** 화면에 보여주는 처리 단계 (파이프라인 다이어그램과 동일) */
export type PipelineStage = 'upload' | 'stt' | 'parse' | 'inference'

/** 분류 요청 전체 상태 */
export type ClassifyStatus =
  | { state: 'idle' }
  | { state: 'running'; stage: PipelineStage }
  | { state: 'success'; result: ClassifyResponse }
  | { state: 'error'; message: string; /** 실패한 단계 */ stage?: PipelineStage }
