import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef } from 'react'
import { sendTurn, type TurnInput } from '@/api/dialog'
import type { PipelineStage } from '@/types/classify'
import type { DialogSlots, IntentKey, Turn, TurnResponse } from '@/types/dialog'
import { todayISO } from '@/utils/date'
import { applyFrames, createInitialSlots } from '@/utils/dialogState'
import { getNextStep } from '@/utils/nextQuestion'

/** 보내는 중인 턴 (응답 오기 전 화면에 먼저 보여줌) */
export type PendingTurn = {
  askedIntent: IntentKey | null
  question: string
  input: TurnInput['kind']
  /** 텍스트 입력이면 입력한 문장 */
  text?: string
  audioUrl?: string
  stage: PipelineStage
}

export type DialogModel = {
  sessionId: string
  callDate: string
  turns: Turn[]
  slots: DialogSlots
  pending: PendingTurn | null
  error: string | null
}

type Action =
  | { type: 'send'; pending: PendingTurn }
  | { type: 'stage'; stage: PipelineStage }
  | { type: 'success'; response: TurnResponse }
  | { type: 'error'; message: string }
  | { type: 'cancel' }
  | { type: 'reset' }

function newSessionId() {
  return globalThis.crypto?.randomUUID?.() ?? `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function createModel(): DialogModel {
  return {
    sessionId: newSessionId(),
    callDate: todayISO(),
    turns: [],
    slots: createInitialSlots(),
    pending: null,
    error: null,
  }
}

/** 턴마다 dispatch 되는 상태 갱신 (프론트로 치면 이 reducer 가 대화 상태 관리의 전부) */
function reducer(model: DialogModel, action: Action): DialogModel {
  switch (action.type) {
    case 'send':
      return { ...model, pending: action.pending, error: null }
    case 'stage':
      return model.pending ? { ...model, pending: { ...model.pending, stage: action.stage } } : model
    case 'success': {
      const { pending } = model
      if (!pending) return model
      const index = model.turns.length + 1
      const { response } = action
      const { slots, changes } = applyFrames(model.slots, response.frames, index)
      const turn: Turn = {
        index,
        askedIntent: pending.askedIntent,
        question: pending.question,
        input: pending.input,
        audioUrl: pending.audioUrl,
        transcript: response.transcript,
        frames: response.frames,
        changes,
        sttEngine: response.sttEngine,
        latencyMs: response.latencyMs,
      }
      return { ...model, turns: [...model.turns, turn], slots, pending: null }
    }
    case 'error':
      return { ...model, pending: null, error: action.message }
    case 'cancel':
      return { ...model, pending: null }
    case 'reset':
      return createModel()
  }
}

/**
 * 상담 대화 한 건을 관리하는 훅
 * - 턴 보내기 → 분류 결과(frames) 받기 → 상태 갱신
 * - 다음 질문은 상태에서 계산 (getNextStep)
 */
export function useDialog() {
  const [model, dispatch] = useReducer(reducer, undefined, createModel)
  const controllerRef = useRef<AbortController | null>(null)
  const busyRef = useRef(false)
  const audioUrls = useRef(new Set<string>())
  // send 안에서 항상 최신 상태를 읽기 위한 사본 (렌더가 끝난 뒤 갱신)
  const modelRef = useRef(model)
  useLayoutEffect(() => {
    modelRef.current = model
  })

  const step = useMemo(() => getNextStep(model.slots), [model.slots])
  const sending = model.pending !== null

  const revokeAll = () => {
    audioUrls.current.forEach((url) => URL.revokeObjectURL(url))
    audioUrls.current.clear()
  }

  const send = useCallback(async (input: TurnInput) => {
    const current = modelRef.current
    const next = getNextStep(current.slots)
    // 같은 순간에 두 번 눌러도 한 번만 보내도록 (렌더 전이라 pending 이 아직 비어 있을 수 있음)
    if (busyRef.current || current.pending || next.type !== 'ask') return
    busyRef.current = true

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
        askedIntent: next.intent,
        question: next.question,
        input: input.kind,
        text: input.kind === 'text' ? input.text : undefined,
        audioUrl,
        stage: input.kind === 'voice' ? 'upload' : 'inference',
      },
    })

    try {
      const response = await sendTurn(
        {
          sessionId: current.sessionId,
          callDate: current.callDate,
          askedIntent: next.intent,
          history: current.turns.map((t) => ({ askedIntent: t.askedIntent, utterance: t.transcript })),
        },
        input,
        { signal: controller.signal, onStage: (stage) => dispatch({ type: 'stage', stage }) },
      )
      if (controller.signal.aborted) return
      dispatch({ type: 'success', response })
    } catch (err) {
      dropAudio()
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.'
      dispatch({ type: 'error', message })
    } finally {
      busyRef.current = false
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [])

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    dispatch({ type: 'cancel' })
  }, [])

  const reset = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    revokeAll()
    dispatch({ type: 'reset' })
  }, [])

  // 페이지를 떠나면 요청 취소 + 음성 URL 정리
  useEffect(
    () => () => {
      controllerRef.current?.abort()
      revokeAll()
    },
    [],
  )

  return { model, step, sending, send, cancel, reset }
}
