import { useState } from 'react'
import { CalendarDays, CircleAlert, Info, RotateCcw, X } from 'lucide-react'
import type { TurnInput } from '@/api/dialog'
import { PageHeader } from '@/components/common/PageHeader'
import { ChatTimeline } from '@/components/dialog/ChatTimeline'
import { Composer } from '@/components/dialog/Composer'
import { StatePanel } from '@/components/dialog/StatePanel'
import { config } from '@/config'
import { ONTOLOGY_VERSION } from '@/constants/ontology'
import { useDialog } from '@/hooks/useDialog'
import { formatKoreanDate } from '@/utils/date'

/** 상담 데모: AI 상담원 질문 → 민원인 응답(음성/텍스트) → 턴마다 분류 → 접수 상태 누적 */
export function ConsultPage() {
  const { model, step, sending, send, cancel, reset } = useDialog()
  const [inputError, setInputError] = useState<string | null>(null)
  const error = inputError ?? model.error
  const lastTurn = model.turns[model.turns.length - 1]
  const askingIntent = model.pending?.askedIntent ?? (step.type === 'ask' ? step.intent : null)

  const handleSend = (input: TurnInput) => {
    setInputError(null)
    send(input)
  }

  const restart = () => {
    setInputError(null)
    reset()
  }

  return (
    <>
      <PageHeader
        title="상담 데모"
        description="AI 상담원이 순서대로 묻고, 민원인 답변을 턴마다 분류해 접수 상태를 채웁니다."
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
              <CalendarDays className="size-3.5 text-slate-400" />
              통화일 {formatKoreanDate(model.callDate)}
            </span>
            <button
              type="button"
              onClick={restart}
              disabled={model.turns.length === 0 && !sending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="size-3.5" />새 상담
            </button>
          </>
        }
      />

      {config.useMock && (
        <div className="mb-6 flex gap-2.5 rounded-xl border border-accent-600/20 bg-accent-50 px-4 py-3 text-sm text-accent-600">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p>
            <b className="font-semibold">Mock 모드</b> — 음성은 녹음 내용과 관계없이 시연용 대화가 순서대로 나오고,
            텍스트는 온톨로지 v{ONTOLOGY_VERSION} 예시 발화만 인식합니다.
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
        <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <ChatTimeline
            turns={model.turns}
            pending={model.pending}
            step={step}
            slots={model.slots}
            onCancel={cancel}
            className="h-[58dvh] min-h-[420px] px-4 py-5 sm:px-6"
          />

          <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-4 sm:px-6">
            {error && (
              <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                <CircleAlert className="mt-0.5 size-4 shrink-0" />
                <p className="flex-1">{error}</p>
                {inputError && (
                  <button type="button" onClick={() => setInputError(null)} aria-label="닫기" className="text-red-400 hover:text-red-600">
                    <X className="size-4" />
                  </button>
                )}
              </div>
            )}
            <Composer step={step} sending={sending} onSend={handleSend} onError={setInputError} onRestart={restart} />
          </div>
        </section>

        <aside className="lg:sticky lg:top-6">
          <StatePanel slots={model.slots} askingIntent={askingIntent} lastTurn={lastTurn} />
        </aside>
      </div>
    </>
  )
}
