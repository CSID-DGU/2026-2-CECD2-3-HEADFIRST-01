import type { ClassifyResponse, PipelineStage } from '@/types/classify'
import type { ClassifyOptions } from './classify'

/**
 * 백엔드가 준비되기 전까지 쓰는 가짜 응답
 * (음성 내용과 무관하게 아래 샘플 중 하나를 돌려줌)
 */
const SAMPLES: Omit<ClassifyResponse, 'requestId' | 'latencyMs'>[] = [
  {
    transcript: '음 그 저기 지하철 이호선 강남역에서 어 지갑을 잃어버렸는데요 어 어디서 찾을 수 있나요',
    normalizedText: '지하철 2호선 강남역에서 지갑을 잃어버렸는데 어디서 찾을 수 있나요',
    intent: { label: '분실물_문의', confidence: 0.94 },
    candidates: [
      { label: '분실물_문의', confidence: 0.94 },
      { label: '역_시설_문의', confidence: 0.04 },
      { label: '기타', confidence: 0.02 },
    ],
    entities: [
      { type: '노선', value: '2호선' },
      { type: '역명', value: '강남역' },
      { type: '물품', value: '지갑' },
    ],
  },
  {
    transcript: '아 네 저 내일 오전 열 시에 그 상담 예약을 좀 하고 싶은데요 가능할까요',
    normalizedText: '내일 오전 10시에 상담 예약을 하고 싶은데 가능할까요',
    intent: { label: '상담_예약', confidence: 0.91 },
    candidates: [
      { label: '상담_예약', confidence: 0.91 },
      { label: '예약_변경', confidence: 0.06 },
      { label: '기타', confidence: 0.03 },
    ],
    entities: [
      { type: '날짜', value: '내일' },
      { type: '시간', value: '오전 10시' },
    ],
  },
  {
    transcript: '어 그러니까 카드로 결제를 했는데 음 두 번 결제가 된 것 같아서요 환불 좀 받을 수 있을까요',
    normalizedText: '카드로 결제를 했는데 두 번 결제된 것 같아서 환불받을 수 있을까요',
    intent: { label: '환불_요청', confidence: 0.88 },
    candidates: [
      { label: '환불_요청', confidence: 0.88 },
      { label: '결제_오류_신고', confidence: 0.1 },
      { label: '기타', confidence: 0.02 },
    ],
    entities: [
      { type: '결제수단', value: '카드' },
      { type: '횟수', value: '두 번' },
    ],
  },
]

const STAGE_DELAYS: [PipelineStage, number][] = [
  ['upload', 500],
  ['stt', 900],
  ['parse', 500],
  ['inference', 1100],
]

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'))
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

export async function mockClassify(file: File, { onStage, signal }: ClassifyOptions): Promise<ClassifyResponse> {
  const latency: Record<PipelineStage, number> = { upload: 0, stt: 0, parse: 0, inference: 0 }

  for (const [stage, ms] of STAGE_DELAYS) {
    onStage?.(stage)
    await wait(ms, signal)
    latency[stage] = ms
  }

  // 파일 이름 길이로 샘플을 골라 같은 파일은 항상 같은 결과가 나오게 함
  const sample = SAMPLES[file.name.length % SAMPLES.length]
  const text = sample.normalizedText ?? sample.transcript

  return {
    ...sample,
    // 엔티티 위치(start/end)를 정제된 문장 기준으로 계산
    entities: sample.entities.map((e) => {
      const start = text.indexOf(e.value)
      return start < 0 ? e : { ...e, start, end: start + e.value.length }
    }),
    requestId: `mock-${Date.now().toString(36)}`,
    latencyMs: {
      stt: latency.stt,
      inference: latency.parse + latency.inference,
      total: Object.values(latency).reduce((a, b) => a + b, 0),
    },
  }
}
