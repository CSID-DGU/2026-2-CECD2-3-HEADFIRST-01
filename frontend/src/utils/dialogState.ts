import { INTENT_MAP, INTENT_ORDER } from '@/constants/ontology'
import type { DialogSlots, Frame, FrameValue, IntentKey, SlotChange, SlotState } from '@/types/dialog'

/*
 * 대화 상태 갱신 규칙 (순수 함수 — 나중에 백엔드로 옮겨도 그대로 쓸 수 있음)
 *
 * - inform    → 값을 넣는다. 이미 다른 값이 있으면 최신 값으로 덮어쓰고(정정) 이전 값은 기록에 남긴다.
 * - uncertain → 이미 값이 있으면 건드리지 않는다. 값이 없으면 '불확실' 로 표시한다.
 * - 부분값(010-????-7777)을 같은 자리 그대로 채운 값(010-1234-7777)은 정정이 아니라 '채움' 으로 본다.
 */

const isKnownIntent = (key: string): key is IntentKey => key in INTENT_MAP

/** 모르는 자리를 '?' 로 둔 부분값인지 */
export function isPartialValue(value: FrameValue): boolean {
  return typeof value === 'string' && value.includes('?')
}

/** 부분값의 '?' 자리만 채운 값인지 (010-????-7777 → 010-1234-7777) */
function completesPartial(partial: FrameValue, next: FrameValue): boolean {
  if (typeof partial !== 'string' || typeof next !== 'string') return false
  if (partial.length !== next.length) return false
  return [...partial].every((ch, i) => ch === '?' || ch === next[i])
}

const hasValue = (slot: SlotState) => slot.status === 'filled' || slot.status === 'partial'

export function createInitialSlots(): DialogSlots {
  const slots = {} as DialogSlots
  for (const key of INTENT_ORDER) slots[key] = { status: 'empty', value: null, previous: [], updatedTurn: null }
  return slots
}

/** 한 턴의 frame 목록을 상태에 반영하고, 바뀐 항목 목록을 함께 돌려준다 */
export function applyFrames(
  slots: DialogSlots,
  frames: Frame[],
  turn: number,
): { slots: DialogSlots; changes: SlotChange[] } {
  const next: DialogSlots = { ...slots }
  const changes: SlotChange[] = []

  for (const frame of frames) {
    if (!isKnownIntent(frame.intent)) continue
    const prev = next[frame.intent]
    const isInform = frame.action === 'inform' && frame.value !== null

    if (isInform) {
      if (hasValue(prev) && prev.value === frame.value) continue // 같은 값을 다시 말함

      const revised = hasValue(prev) && !(prev.status === 'partial' && completesPartial(prev.value, frame.value))
      next[frame.intent] = {
        status: isPartialValue(frame.value) ? 'partial' : 'filled',
        value: frame.value,
        previous: revised ? [...prev.previous, { value: prev.value, turn: prev.updatedTurn ?? turn }] : prev.previous,
        updatedTurn: turn,
      }
      changes.push({ intent: frame.intent, kind: revised ? 'revised' : 'filled', from: prev.value, to: frame.value })
      continue
    }

    // uncertain
    if (hasValue(prev)) continue // 이미 받은 값은 유지
    next[frame.intent] = { ...prev, status: 'uncertain', value: null, updatedTurn: turn }
    changes.push({ intent: frame.intent, kind: 'uncertain', from: null, to: null })
  }

  return { slots: next, changes }
}

/** 값 → 화면 표시 문자열 */
export function formatFrameValue(intent: IntentKey, value: FrameValue): string {
  if (value === null) return '—'
  if (typeof value === 'boolean') {
    if (intent === 'consent') return value ? '동의' : '동의 안 함'
    return value ? '예' : '아니오'
  }
  return value
}

export function countFilled(slots: DialogSlots): number {
  return INTENT_ORDER.filter((k) => hasValue(slots[k])).length
}
