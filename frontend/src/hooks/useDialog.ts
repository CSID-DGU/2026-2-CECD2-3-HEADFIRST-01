import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from 'react'
import { ApiError, type ClientErrorCode } from '@/api/client'
import { createSession, getSession, sendTurn, type TurnInput } from '@/api/session'
import { INTENT_MAP } from '@/constants/ontology'
import type { Frame as ApiFrame, NextQuestion, SessionDetail, SessionSnapshot, SlotValues, TurnResult } from '@/types/api'
import type { PipelineStage } from '@/types/classify'
import type { DialogSlots, Frame, IntentKey, Turn } from '@/types/dialog'
import { todayISO } from '@/utils/date'
import {
  applyServerRule,
  createEmptyValues,
  createInitialSlots,
  reconcileSlots,
  syncSlots,
} from '@/utils/dialogState'
import type { NextStep } from '@/utils/nextQuestion'

const SESSION_KEY = 'consult-session-id'

/** 보내는 중인 턴 (응답 오기 전 화면에 먼저 보여줌) */
export type PendingTurn = {
  askedIntent: IntentKey
  question: string
  input: TurnInput['kind']
  /** 텍스트 입력이면 입력한 문장 */
  text?: string
  audioUrl?: string
  stage: PipelineStage
}

export type DialogError = {
  message: string
  code: ClientErrorCode
  /** 같은 발화를 다시 보내도 되는지 (분류기 오류·연결 실패) */
  retryable: boolean
}

export type DialogStep =
  | { type: 'loading' } // 첫 세션 만드는 중·복원 중
  | { type: 'unavailable' } // 세션을 못 만듦 (서버 꺼짐 등)
  | NextStep

export type DialogModel = {
  status: 'loading' | 'ready' | 'failed'
  sessionId: string | null
  /** 프론트 오늘 날짜 (서버 통화일은 응답에 없음) */
  callDate: string
  /** 마지막으로 받은 서버 slotValues (다음 턴 비교 기준) */
  values: SlotValues
  slots: DialogSlots
  turns: Turn[]
  nextQuestion: NextQuestion | null
  done: boolean
  pending: PendingTurn | null
  error: DialogError | null
}

type Action =
  | { type: 'loading'; fresh: boolean }
  | { type: 'loaded'; session: SessionSnapshot | SessionDetail }
  | { type: 'failed'; error: DialogError }
  | { type: 'send'; pending: PendingTurn }
  | { type: 'stage'; stage: PipelineStage }
  | { type: 'success'; result: TurnResult }
  | { type: 'error'; error: DialogError }
  | { type: 'cancel' }

/* ---------- 변환 ---------- */

const toUiFrames = (frames: ApiFrame[]): Frame[] =>
  frames.map((f) => ({ intent: f.slot, action: f.action, value: f.value }))

const questionOf = (slot: IntentKey) => INTENT_MAP[slot].question

const RETRYABLE: ClientErrorCode[] = ['LLM_FAILED', 'LLM_TIMEOUT', 'NETWORK']

function toDialogError(err: unknown): DialogError {
  if (err instanceof ApiError) {
    return { message: err.message, code: err.code, retryable: RETRYABLE.includes(err.code) }
  }
  const message = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.'
  return { message, code: 'UNKNOWN', retryable: false }
}

const isAbort = (err: unknown) => err instanceof DOMException && err.name === 'AbortError'

/* ---------- sessionId 보관 ---------- */

function readSavedId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

function saveId(id: string) {
  try {
    sessionStorage.setItem(SESSION_KEY, id)
  } catch {
    /* 저장 실패 시 새로고침 복원만 안 됨 */
  }
}

function clearSavedId() {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* 무시 */
  }
}

/* ---------- 상태 ---------- */

function createModel(): DialogModel {
  return {
    status: 'loading',
    sessionId: null,
    callDate: todayISO(),
    values: createEmptyValues(),
    slots: createInitialSlots(),
    turns: [],
    nextQuestion: null,
    done: false,
    pending: null,
    error: null,
  }
}

/** 서버 세션 → 화면 상태. turns가 있으면 frames를 서버 규칙대로 다시 돌려서 정정 이력까지 복원 */
function restore(model: DialogModel, session: SessionSnapshot | SessionDetail): DialogModel {
  const records = 'turns' in session ? session.turns : []
  const known = new Map(model.turns.map((t) => [t.index, t]))

  let values = createEmptyValues()
  let slots = createInitialSlots()
  const turns: Turn[] = []

  for (const t of records) {
    const after = applyServerRule(values, t.frames)
    const frames = toUiFrames(t.frames)
    const r = reconcileSlots(slots, values, after, frames, t.turnIndex)
    const prev = known.get(t.turnIndex) // 이미 화면에 있던 턴이면 음성·처리 시간 유지
    turns.push({
      index: t.turnIndex,
      askedIntent: t.requestedSlot,
      question: t.question ?? prev?.question ?? questionOf(t.requestedSlot),
      input: prev?.input ?? 'text',
      audioUrl: prev?.audioUrl,
      transcript: t.transcript,
      frames,
      changes: r.changes,
      sttEngine: prev?.sttEngine,
      latencyMs: prev?.latencyMs,
    })
    values = after
    slots = r.slots
  }

  return {
    ...model,
    status: 'ready',
    sessionId: session.sessionId,
    values: session.slotValues,
    slots: syncSlots(slots, session.slotValues),
    turns,
    nextQuestion: session.nextQuestion,
    done: session.done,
    pending: null,
    error: null,
  }
}

function reducer(model: DialogModel, action: Action): DialogModel {
  switch (action.type) {
    case 'loading':
      return action.fresh ? createModel() : { ...model, status: 'loading', pending: null, error: null }
    case 'loaded':
      return restore(model, action.session)
    case 'failed':
      return { ...model, status: 'failed', pending: null, error: action.error }
    case 'send':
      return { ...model, pending: action.pending, error: null }
    case 'stage':
      return model.pending ? { ...model, pending: { ...model.pending, stage: action.stage } } : model
    case 'success': {
      const { pending } = model
      if (!pending) return model
      const r = action.result
      const frames = toUiFrames(r.frames)
      const { slots, changes } = reconcileSlots(model.slots, model.values, r.slotValues, frames, r.turnIndex)
      const turn: Turn = {
        index: r.turnIndex,
        askedIntent: r.requestedSlot,
        question: pending.question,
        input: pending.input,
        audioUrl: pending.audioUrl,
        transcript: r.transcript,
        frames,
        changes,
        sttEngine: r.sttEngine ?? undefined,
        latencyMs: {
          stt: r.timingMs?.stt ?? undefined,
          inference: r.timingMs?.llm ?? undefined,
          total: r.timingMs?.total ?? undefined,
        },
      }
      return {
        ...model,
        turns: [...model.turns, turn],
        slots,
        values: r.slotValues,
        nextQuestion: r.nextQuestion,
        done: r.done,
        pending: null,
      }
    }
    case 'error':
      return { ...model, pending: null, error: action.error }
    case 'cancel':
      return { ...model, pending: null }
  }
}

function toStep(model: DialogModel): DialogStep {
  if (model.status === 'failed') return { type: 'unavailable' }
  // 취소 후 다시 불러오는 중에는 기존 화면 유지 (sessionId가 있으면)
  if (model.sessionId === null) return { type: 'loading' }
  if (model.done || !model.nextQuestion) return { type: 'done', reason: 'complete' }
  return { type: 'ask', intent: model.nextQuestion.slot, question: model.nextQuestion.text, retry: false }
}

/**
 * 상담 대화 한 건을 관리하는 훅
 * - 화면 진입: 저장된 sessionId가 있으면 복원, 없거나 만료면 새 세션
 * - 턴 보내기 → 서버 slotValues·nextQuestion·done으로 갱신
 */
export function useDialog() {
  const [model, dispatch] = useReducer(reducer, undefined, createModel)
  const controllerRef = useRef<AbortController | null>(null)
  const busyRef = useRef(false)
  const audioUrls = useRef(new Set<string>())
  const lastInputRef = useRef<TurnInput | null>(null)
  // send 안에서 항상 최신 상태를 읽기 위한 사본
  const modelRef = useRef(model)
  useLayoutEffect(() => {
    modelRef.current = model
  })

  const step = toStep(model)
  const sending = model.pending !== null

  const revokeAll = () => {
    audioUrls.current.forEach((url) => URL.revokeObjectURL(url))
    audioUrls.current.clear()
  }

  /** resume: 저장된 세션 복원 시도 / new: 무조건 새 세션 */
  const start = useCallback(async (mode: 'resume' | 'new') => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const { signal } = controller
    dispatch({ type: 'loading', fresh: mode === 'new' })

    try {
      let session: SessionSnapshot | SessionDetail | null = null
      const saved = mode === 'resume' ? readSavedId() : null
      if (saved) {
        try {
          session = await getSession(saved, { signal })
        } catch (err) {
          if (!(err instanceof ApiError && err.code === 'SESSION_NOT_FOUND')) throw err
          clearSavedId()
        }
      }
      if (!session) session = await createSession({ signal })
      if (signal.aborted) return
      saveId(session.sessionId)
      dispatch({ type: 'loaded', session })
    } catch (err) {
      if (isAbort(err)) return
      dispatch({ type: 'failed', error: toDialogError(err) })
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [])

  const send = useCallback(async (input: TurnInput) => {
    const current = modelRef.current
    const q = current.nextQuestion
    // 같은 순간에 두 번 눌러도 한 번만 보내도록
    if (busyRef.current || current.pending || current.status !== 'ready' || current.done || !q || !current.sessionId) {
      return
    }
    busyRef.current = true
    lastInputRef.current = input

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    let audioUrl: string | undefined
    if (input.kind === 'voice') {
      audioUrl = URL.createObjectURL(input.audio)
      audioUrls.current.add(audioUrl)
    }
    const dropAudio = () => {
      if (!audioUrl) return
      URL.revokeObjectURL(audioUrl)
      audioUrls.current.delete(audioUrl)
    }

    dispatch({
      type: 'send',
      pending: {
        askedIntent: q.slot,
        question: q.text,
        input: input.kind,
        text: input.kind === 'text' ? input.text : undefined,
        audioUrl,
        stage: input.kind === 'voice' ? 'upload' : 'inference',
      },
    })

    try {
      const result = await sendTurn(current.sessionId, input, {
        signal: controller.signal,
        onStage: (stage) => dispatch({ type: 'stage', stage }),
      })
      if (controller.signal.aborted) return
      dispatch({ type: 'success', result })
    } catch (err) {
      dropAudio()
      if (isAbort(err)) return
      const error = toDialogError(err)
      if (error.code === 'SESSION_NOT_FOUND') clearSavedId()
      dispatch({ type: 'error', error })
    } finally {
      busyRef.current = false
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [])

  /** 분류기 오류·연결 실패 후 같은 발화 다시 보내기 */
  const retry = useCallback(() => {
    const input = lastInputRef.current
    if (input) void send(input)
  }, [send])

  /** 보내는 중 취소. 서버는 이미 처리했을 수 있으므로 상태를 다시 불러온다 */
  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    dispatch({ type: 'cancel' })
    void start('resume')
  }, [start])

  /** 새 상담 */
  const reset = useCallback(() => {
    revokeAll()
    clearSavedId()
    void start('new')
  }, [start])

  /** 세션 시작 실패 후 다시 시도 */
  const reload = useCallback(() => {
    void start('resume')
  }, [start])

  // 화면 진입 시 세션 시작, 떠나면 요청 취소 + 음성 URL 정리
  useEffect(() => {
    void start('resume')
    return () => {
      controllerRef.current?.abort()
      revokeAll()
    }
  }, [start])

    return { model, step, sending, loading: model.status === 'loading', send, cancel, reset, retry, reload }
}