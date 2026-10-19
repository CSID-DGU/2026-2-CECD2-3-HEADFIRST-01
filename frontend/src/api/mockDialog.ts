import { INTENTS, type OntologyExample } from '@/constants/ontology'
import type { PipelineStage } from '@/types/classify'
import type { Frame, IntentKey, TurnRequest, TurnResponse } from '@/types/dialog'
import { diffISODays, shiftISODate } from '@/utils/date'
import type { SendTurnOptions, TurnInput } from './dialog'

/*
 * 백엔드가 준비되기 전까지 쓰는 가짜 분류기
 *
 * - 음성 입력: 녹음 내용과 관계없이, 물어본 의도별로 아래 SCRIPT 의 발화를 순서대로 돌려준다.
 *   (몇 번째로 같은 질문을 받았는지에 따라 다음 발화로 넘어감)
 * - 텍스트 입력: 온톨로지 예시 발화와 같은 문장이면 그 정답 frame 을, 아니면 uncertain 을 돌려준다.
 */

const inform = (intent: IntentKey, value: string | boolean): Frame => ({ intent, action: 'inform', value })
const uncertain = (intent: IntentKey): Frame => ({ intent, action: 'uncertain', value: null })

type ScriptLine = { utterance: string; frames: (callDate: string) => Frame[] }

/** 시연용 대화 — 헷갈리는 발화, 다중 의도, 이전 턴 정정을 일부러 섞음 */
const SCRIPT: Record<IntentKey, ScriptLine[]> = {
  consent: [{ utterance: '뭐 그러던가요', frames: () => [inform('consent', true)] }], // 애매한 긍정
  name: [
    {
      // 한 발화에 의도 두 개 → 생년월일 질문은 건너뜀
      utterance: '김천일이고 오공년생 칠월 이일이에요',
      frames: () => [inform('name', '김천일'), inform('birth_date', '1950-07-02')],
    },
  ],
  birth_date: [{ utterance: '오공년생 칠월 이일', frames: () => [inform('birth_date', '1950-07-02')] }],
  phone: [
    { utterance: '공일공 일이삼 사오육', frames: () => [uncertain('phone')] }, // 자릿수 부족
    { utterance: '공일공에 일이삼사에 오육칠팔', frames: () => [inform('phone', '010-1234-5678')] },
  ],
  complaint_type: [
    { utterance: '집 앞 길이 움푹 패여서 할머니가 넘어질 뻔했어', frames: () => [inform('complaint_type', '도로·보도 파손')] },
  ],
  occurred_date: [
    { utterance: '추석 지나고 한 닷새 됐나', frames: () => [uncertain('occurred_date')] }, // 근사 표현
    {
      // 상대 날짜 + 앞 턴에서 말한 전화번호 정정 (이전 값을 알아야 풀 수 있음 → history 필요)
      utterance: '그저께부터요 아 그리고 아까 전화번호 끝자리 오육칠팔 아니고 오육칠구예요',
      frames: (callDate) => [inform('occurred_date', shiftISODate(callDate, -2)), inform('phone', '010-1234-5679')],
    },
  ],
  description: [
    {
      utterance: '우리 집 앞에 길이 움푹 패여서 어제 할머니가 넘어질 뻔했어 그거 좀 고쳐줘',
      frames: () => [inform('description', '집 앞 도로가 패여 보행자가 넘어질 뻔함')],
    },
  ],
  reply_channel: [{ utterance: '문자는 내가 못 봐요', frames: () => [inform('reply_channel', '전화')] }], // 부정으로 답함
}

/** 텍스트 입력에서 찾아볼 발화들 (온톨로지 예시 + 시연 대화) */
const KNOWN_UTTERANCES: { utterance: string; frames: (callDate: string) => Frame[] }[] = [
  ...INTENTS.flatMap((d) => d.examples.map(exampleToLine)),
  ...Object.values(SCRIPT).flat(),
]

/** 상대 날짜 예시는 오늘 통화 기준으로 날짜를 다시 계산 */
function exampleToLine(ex: OntologyExample): ScriptLine {
  return {
    utterance: ex.utterance,
    frames: (callDate) => {
      if (!ex.callDate) return ex.frames
      const offset = diffISODays(ex.callDate, callDate)
      return ex.frames.map((f) =>
        f.intent === 'occurred_date' && typeof f.value === 'string' ? { ...f, value: shiftISODate(f.value, offset) } : f,
      )
    },
  }
}

/** 띄어쓰기·문장부호 차이는 무시하고 비교 */
const normalize = (s: string) => s.replace(/[\s.,!?~·…'"]/g, '')

/** 질문한 의도는 항상 맨 앞에 출력 (온톨로지 규칙) */
function putAskedFirst(frames: Frame[], asked: IntentKey | null): Frame[] {
  if (!asked) return frames
  const own = frames.filter((f) => f.intent === asked)
  const rest = frames.filter((f) => f.intent !== asked)
  return [...(own.length ? own : [uncertain(asked)]), ...rest]
}

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

export async function mockSendTurn(
  req: TurnRequest,
  input: TurnInput,
  { onStage, signal }: SendTurnOptions,
): Promise<TurnResponse> {
  let stt = 0
  let inference = 0
  for (const [stage, ms] of STAGE_DELAYS[input.kind]) {
    onStage?.(stage)
    await wait(ms, signal)
    if (stage === 'inference') inference += ms
    else stt += ms
  }

  let transcript: string
  let frames: Frame[]

  if (input.kind === 'text') {
    transcript = input.text.trim()
    const hit = KNOWN_UTTERANCES.find((line) => normalize(line.utterance) === normalize(transcript))
    frames = hit ? hit.frames(req.callDate) : []
  } else {
    const asked = req.askedIntent
    const lines = asked ? SCRIPT[asked] : []
    const attempt = req.history.filter((h) => h.askedIntent === asked).length
    const line = lines[Math.min(attempt, lines.length - 1)]
    transcript = line?.utterance ?? '(인식된 말소리가 없습니다)'
    frames = line ? line.frames(req.callDate) : []
  }

  return {
    transcript,
    frames: putAskedFirst(frames, req.askedIntent),
    sttEngine: input.kind === 'voice' ? 'mock' : undefined,
    latencyMs: { stt: input.kind === 'voice' ? stt : undefined, inference, total: stt + inference },
  }
}
