import { INTENT_MAP, INTENT_ORDER } from '@/constants/ontology'
import type { DialogSlots, IntentKey } from '@/types/dialog'

export type NextStep =
  | { type: 'ask'; intent: IntentKey; question: string; retry: boolean }
  | { type: 'done'; reason: 'complete' | 'no_consent' }

/*
 * 다음에 AI가 무엇을 물을지 정하는 곳 (= 대화 정책)
 *
 * 재질문·확인 질문·같은 질문 반복 제한 같은 정책은 분류기 완성 후 팀에서 정하기로 했으므로
 * 지금은 가장 단순한 규칙만 둔다. 정책이 정해지면 이 파일만 바꾸면 된다.
 *
 * 현재 규칙
 * 1. 개인정보 수집에 동의하지 않으면 접수를 끝낸다.
 * 2. 순서대로 보면서 값이 없는(empty·uncertain) 첫 항목을 묻는다.
 * 3. 부분값(010-????-7777)은 일단 받은 것으로 보고 넘어간다.  ← 팀 미결 사항
 */
export function getNextStep(slots: DialogSlots): NextStep {
  if (slots.consent.status === 'filled' && slots.consent.value === false) {
    return { type: 'done', reason: 'no_consent' }
  }

  const intent = INTENT_ORDER.find((key) => {
    const { status } = slots[key]
    return status === 'empty' || status === 'uncertain'
  })
  if (!intent) return { type: 'done', reason: 'complete' }

  const retry = slots[intent].status === 'uncertain'
  const base = INTENT_MAP[intent].question
  return {
    type: 'ask',
    intent,
    // 같은 문장을 그대로 반복하지 않도록 앞말만 붙임
    question: retry ? `죄송하지만 다시 한번 여쭤볼게요. ${base}` : base,
    retry,
  }
}
