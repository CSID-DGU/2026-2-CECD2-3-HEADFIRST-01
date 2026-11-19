import { INTENTS, INTENT_MAP, type OntologyExample } from '@/constants/ontology'
import type { PipelineStage } from '@/types/classify'
import type {
  Frame,
  SessionDetail,
  SessionSnapshot,
  SlotName,
  SlotValue,
  SlotValues,
  TurnRecord,
  TurnResult,
} from '@/types/api'
import { diffISODays, shiftISODate } from '@/utils/date'
import { ApiError } from './client'
import type { RequestOptions, SendTurnOptions, TurnInput } from './session'

/*
 * 백엔드 규칙(backend/session.py)을 흉내 내는 가짜 세션 서버
 *
 * - 다음 질문: 아직 묻지 않았고 완료되지 않은 첫 슬롯 (슬롯마다 한 번만)
 * - 완료: 값이 있고 '?'가 없음
 * - inform만 반영해 덮어쓰기. 이전 값에 '?'가 있고 길이가 같으면 '?' 자리만 채움
 * - uncertain은 무시
 * - 음성: 녹음 내용과 관계없이 지금 묻는 슬롯의 SCRIPT 발화를 돌려줌
 * - 텍스트: 온톨로지 예시·시연 발화와 같은 문장만 인식, 나머지는 uncertain
 */

const SLOT_ORDER: SlotName[] = [
  'consent',
  'name',
  'birth_date',
  'phone',
  'complaint_type',
  'occurred_date',
  'description',
  'reply_channel',
]

const STORE_KEY = 'mock-sessions'
const EXPIRE_MS = 30 * 60 * 1000

/* ---------- 시연 대화 ---------- */

const inform = (slot: SlotName, value: string | boolean): Frame => ({ slot, action: 'inform', value })
const uncertain = (slot: SlotName): Frame => ({ slot, action: 'uncertain', value: null })

type ScriptLine = { utterance: string; frames: (callDate: string) => Frame[] }

const SCRIPT: Record<SlotName, ScriptLine> = {
  consent: { utterance: '뭐 그러던가요', frames: () => [inform('consent', true)] },
  name: {
    utterance: '김천일이고 오공년생 칠월 이일이에요',
    frames: () => [inform('name', '김천일'), inform('birth_date', '1950-07-02')],
  },
  // name 턴에서 채워지므로 시연 흐름에서는 묻지 않음
  birth_date: { utterance: '오공년생 칠월 이일', frames: () => [inform('birth_date', '1950-07-02')] },
  phone: {
    utterance: '공일공에 가운데는 잘 모르겠고 끝은 오육칠팔이요',
    frames: () => [inform('phone', '010-????-5678')],
  },
  complaint_type: {
    utterance: '집 앞 길이 움푹 패였어요 아 전화번호 가운데는 일이삼사예요',
    frames: () => [inform('complaint_type', '도로·보도 파손'), inform('phone', '010-1234-????')],
  },
  occurred_date: { utterance: '추석 지나고 한 닷새 됐나', frames: () => [uncertain('occurred_date')] },
  description: {
    utterance: '우리 집 앞에 길이 움푹 패여서 어제 할머니가 넘어질 뻔했어 아 그리고 전화번호 끝자리 오육칠팔 아니고 오육칠구예요',
    frames: () => [inform('description', '집 앞 도로가 패여 보행자가 넘어질 뻔함'), inform('phone', '010-1234-5679')],
  },
  reply_channel: { utterance: '문자는 내가 못 봐요', frames: () => [inform('reply_channel', '전화')] },
}

/** 상대 날짜 예시는 오늘 통화 기준으로 다시 계산 */
function exampleToLine(ex: OntologyExample): ScriptLine {
  return {
    utterance: ex.utterance,
    frames: (callDate) => {
      const offset = ex.callDate ? diffISODays(ex.callDate, callDate) : 0
      return ex.frames.map((f) => ({
        slot: f.intent as SlotName,
        action: f.action,
        value:
          offset && f.intent === 'occurred_date' && typeof f.value === 'string' ? shiftISODate(f.value, offset) : f.value,
      }))
    },
  }
}

const KNOWN_UTTERANCES: ScriptLine[] = [
  ...INTENTS.flatMap((d) => d.examples.map(exampleToLine)),
  ...Object.values(SCRIPT),
]

const normalize = (s: string) => s.replace(/[\s.,!?~·…'"]/g, '')

/** 질문한 슬롯은 항상 맨 앞 */
function putAskedFirst(frames: Frame[], asked: SlotName): Frame[] {
  const own = frames.filter((f) => f.slot === asked)
  const rest = frames.filter((f) => f.slot !== asked)
  return [...(own.length ? own : [uncertain(asked)]), ...rest]
}

/* ---------- 세션 저장소 (sessionStorage) ---------- */

type MockSession = {
  sessionId: string
  slotValues: SlotValues
  asked: SlotName[]
  turns: TurnRecord[]
  updatedAt: number
}

function loadAll(): Record<string, MockSession> {
  try {
    return JSON.parse(sessionStorage.getItem(STORE_KEY) ?? '{}') as Record<string, MockSession>
  } catch {
    return {}
  }
}

function saveOne(s: MockSession) {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ ...loadAll(), [s.sessionId]: s }))
  } catch {
    /* 저장 실패 시 새로고침 복원만 안 됨 */
  }
}

function findSession(sessionId: string): MockSession {
  const s = loadAll()[sessionId]
  if (!s || Date.now() - s.updatedAt > EXPIRE_MS) {
    throw new ApiError('세션이 없거나 만료되었습니다. 새 대화를 시작해 주세요.', 404, 'SESSION_NOT_FOUND')
  }
  return s
}

/* ---------- 서버 규칙 ---------- */

const pad = (n: number) => String(n).padStart(2, '0')

function newSessionId(): string {
  const d = new Date()
  const date = `${pad(d.getFullYear() % 100)}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
  const time = `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  const rand = Math.random().toString(16).slice(2, 8).padEnd(6, '0')
  return `${date}-${time}-${rand}`
}

/** 로컬 기준 오늘 YYYY-MM-DD */
const todayISO = () => new Date().toLocaleDateString('sv-SE')

const isComplete = (v: SlotValue) => v !== null && !(typeof v === 'string' && v.includes('?'))

function nextSlot(s: MockSession): SlotName | null {
  return SLOT_ORDER.find((slot) => !s.asked.includes(slot) && !isComplete(s.slotValues[slot])) ?? null
}

function questionText(slot: SlotName): string {
  return INTENT_MAP[slot].question
}

function applyFrames(values: SlotValues, frames: Frame[]): SlotValues {
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

function snapshot(s: MockSession): SessionSnapshot {
  const slot = nextSlot(s)
  return {
    sessionId: s.sessionId,
    slotOrder: [...SLOT_ORDER],
    slotValues: { ...s.slotValues },
    nextQuestion: slot ? { slot, text: questionText(slot) } : null,
    done: slot === null,
  }
}

/* ---------- 지연 ---------- */

const STAGE_DELAYS: Record<TurnInput['kind'], [PipelineStage, number][]> = {
  voice: [
    ['upload', 350],
    ['stt', 800],
    ['inference', 900],
  ],
  text: [['inference', 700]],
}

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

/* ---------- API ---------- */

export async function createSession({ signal }: RequestOptions = {}): Promise<SessionSnapshot> {
  await wait(150, signal)
  const s: MockSession = {
    sessionId: newSessionId(),
    slotValues: Object.fromEntries(SLOT_ORDER.map((k) => [k, null])) as SlotValues,
    asked: [],
    turns: [],
    updatedAt: Date.now(),
  }
  saveOne(s)
  return snapshot(s)
}

export async function getSession(sessionId: string, { signal }: RequestOptions = {}): Promise<SessionDetail> {
  await wait(100, signal)
  const s = findSession(sessionId)
  return { ...snapshot(s), turns: s.turns }
}

export async function sendTurn(
  sessionId: string,
  input: TurnInput,
  { onStage, signal }: SendTurnOptions = {},
): Promise<TurnResult> {
  const s = findSession(sessionId)
  const requested = nextSlot(s)
  if (!requested) throw new ApiError('이미 끝난 대화입니다.', 409, 'SESSION_DONE')
  if (input.kind === 'text' && !input.text.trim()) {
    throw new ApiError('요청 형식이 올바르지 않습니다.', 422, 'INVALID_REQUEST')
  }

  let stt = 0
  let llm = 0
  for (const [stage, ms] of STAGE_DELAYS[input.kind]) {
    onStage?.(stage)
    await wait(ms, signal)
    if (stage === 'inference') llm += ms
    else stt += ms
  }

  const callDate = todayISO()
  let transcript: string
  let frames: Frame[]
  if (input.kind === 'text') {
    transcript = input.text.trim()
    const hit = KNOWN_UTTERANCES.find((line) => normalize(line.utterance) === normalize(transcript))
    frames = hit ? hit.frames(callDate) : []
  } else {
    transcript = SCRIPT[requested].utterance
    frames = SCRIPT[requested].frames(callDate)
  }
  frames = putAskedFirst(frames, requested)

  s.slotValues = applyFrames(s.slotValues, frames)
  s.asked.push(requested)
  const turnIndex = s.turns.length + 1
  s.turns.push({ turnIndex, requestedSlot: requested, transcript, frames, question: questionText(requested) })
  s.updatedAt = Date.now()
  saveOne(s)

  const { slotValues, nextQuestion, done } = snapshot(s)
  return {
    turnIndex,
    requestedSlot: requested,
    transcript,
    frames,
    slotValues,
    nextQuestion,
    done,
    sttEngine: input.kind === 'voice' ? 'mock' : null,
    timingMs: { stt: input.kind === 'voice' ? stt : null, llm, total: stt + llm },
  }
}