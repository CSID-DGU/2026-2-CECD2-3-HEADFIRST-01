import { INTENT_MAP, INTENT_ORDER } from '@/constants/ontology'
import type { Frame as ApiFrame, SlotValues } from '@/types/api'
import type { DialogSlots, Frame, FrameValue, IntentKey, SlotChange, SlotState } from '@/types/dialog'

/*
 * 대화 상태 규칙
 *
 * 값은 서버 slotValues가 정답이고, 화면 상태는 턴 전후 값을 비교해서 만든다.
 * - 값이 새로 생김 / 부분값의 '?' 자리만 채워짐 → 채움
 * - 다른 값으로 바뀜 → 정정 (이전 값은 기록에 남김)
 * - 값이 그대로 비어 있고 uncertain frame이 있음 → 불확실 (서버는 다시 묻지 않으므로 계속 유지)
 */

/** 모르는 자리를 '?'로 둔 부분값인지 */
export function isPartialValue(value: FrameValue): boolean {
  return typeof value === 'string' && value.includes('?')
}

/** 부분값의 '?' 자리만 채운 값인지 (010-????-7777 → 010-1234-7777) */
function fillsPartial(partial: FrameValue, next: FrameValue): boolean {
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

export function createEmptyValues(): SlotValues {
  return Object.fromEntries(INTENT_ORDER.map((k) => [k, null])) as SlotValues
}

/**
 * 서버 규칙 (backend/session.py)
 * - inform만 반영해 덮어쓴다. uncertain은 무시
 * - 이전 값에 '?'가 있고 길이가 같으면 '?' 자리만 새 값으로 채운다
 */
export function applyServerRule(values: SlotValues, frames: ApiFrame[]): SlotValues {
  const next = { ...values }
  for (const f of frames) {
    if (f.action !== 'inform') continue
    const prev = next[f.slot]
    if (typeof prev === 'string' && prev.includes('?') && typeof f.value === 'string' && f.value.length === prev.length) {
      const fill = f.value
      next[f.slot] = [...prev].map((c, i) => (c === '?' ? fill[i] : c)).join('')
    } else {
      next[f.slot] = f.value
    }
  }
  return next
}

/** 턴 전후 서버 값을 비교해 화면 상태와 바뀐 항목 목록을 만든다 */
export function reconcileSlots(
  slots: DialogSlots,
  before: SlotValues,
  after: SlotValues,
  frames: Frame[],
  turn: number,
): { slots: DialogSlots; changes: SlotChange[] } {
  const next: DialogSlots = { ...slots }
  const changes: SlotChange[] = []
  // frame 순서(질문한 슬롯이 맨 앞)를 먼저, 나머지는 온톨로지 순서
  const order = [...new Set<IntentKey>([...frames.map((f) => f.intent), ...INTENT_ORDER])]

  for (const key of order) {
    if (!(key in INTENT_MAP)) continue
    const from = before[key] ?? null
    const to = after[key] ?? null
    const prev = next[key]

    if (from !== to) {
      if (to === null) {
        next[key] = { ...prev, status: 'empty', value: null, updatedTurn: turn }
        continue
      }
      const revised = from !== null && !(isPartialValue(from) && fillsPartial(from, to))
      next[key] = {
        status: isPartialValue(to) ? 'partial' : 'filled',
        value: to,
        previous: revised ? [...prev.previous, { value: from, turn: prev.updatedTurn ?? turn }] : prev.previous,
        updatedTurn: turn,
      }
      changes.push({ intent: key, kind: revised ? 'revised' : 'filled', from, to })
      continue
    }

    const uncertain = to === null && frames.some((f) => f.intent === key && f.action === 'uncertain')
    if (uncertain) {
      next[key] = { ...prev, status: 'uncertain', value: null, updatedTurn: turn }
      changes.push({ intent: key, kind: 'uncertain', from: null, to: null })
    }
  }

  return { slots: next, changes }
}

/** 화면 상태의 값을 서버 값에 강제로 맞춘다 (복원 후 안전장치) */
export function syncSlots(slots: DialogSlots, server: SlotValues): DialogSlots {
  const next: DialogSlots = { ...slots }
  for (const key of INTENT_ORDER) {
    const v = server[key] ?? null
    if (next[key].value === v) continue
    next[key] = { ...next[key], value: v, status: v === null ? 'empty' : isPartialValue(v) ? 'partial' : 'filled' }
  }
  return next
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