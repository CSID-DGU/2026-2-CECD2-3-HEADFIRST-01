import { useState } from 'react'
import { CalendarDays, CircleAlert, LoaderCircle, RefreshCw, RotateCcw, X } from 'lucide-react'
import type { TurnInput } from '@/api/session'
import { PageHeader } from '@/components/common/PageHeader'
import { ChatTimeline } from '@/components/dialog/ChatTimeline'
import { Composer } from '@/components/dialog/Composer'
import { StatePanel } from '@/components/dialog/StatePanel'
import { useDialog } from '@/hooks/useDialog'
import { formatKoreanDate } from '@/utils/date'

/** 상담 데모: AI 상담원 질문 → 민원인 응답(음성/텍스트) → 턴마다 분류 → 접수 상태 누적 */
export function ConsultPage() {
  const { model, step, sending, loading, send, cancel, reset, retry, reload } = useDialog()
  const [inputError, setInputError] = useState<string | null>(null)
  const lastTurn = model.turns[model.turns.length - 1]
  const askingIntent = model.pending?.askedIntent ?? (step.type === 'ask' ? step.intent : null)

  // 세션 시작 실패는 대화창 자리에 따로 보여주므로 배너에서는 뺌
  const apiError = step.type === 'unavailable' ? null : model.error
  const needsNewSession = apiError?.code === 'SESSION_NOT_FOUND' || apiError?.code === 'SESSION_DONE'

  const handleSend = (input: TurnInput) => {
    setInputError(null)
    send(input)
  }

  const restart = () => {
    setInputError(null)
    reset()
  }

  const handleRetry = () => {
    setInputError(null)
    retry()
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
              disabled={loading || (model.turns.length === 0 && !sending)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="size-3.5" />새 상담
            </button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
        <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {step.type === 'loading' ? (
            <div className="flex h-[58dvh] min-h-[420px] flex-col items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-6 animate-spin text-slate-400" />
              상담을 준비하는 중입니다…
            </div>
          ) : step.type === 'unavailable' ? (
            <div className="flex h-[58dvh] min-h-[420px] flex-col items-center justify-center gap-4 px-6 text-center">
              <CircleAlert className="size-8 text-red-400" />
              <p className="text-sm text-slate-700">{model.error?.message ?? '상담을 시작할 수 없습니다.'}</p>
              <button
                type="button"
                onClick={reload}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                <RefreshCw className="size-3.5" />
                다시 시도
              </button>
            </div>
          ) : (
            <>
              <ChatTimeline
                turns={model.turns}
                pending={model.pending}
                step={step}
                slots={model.slots}
                onCancel={cancel}
                className="h-[58dvh] min-h-[420px] px-4 py-5 sm:px-6"
              />

              <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-4 sm:px-6">
                {inputError && (
                  <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                    <CircleAlert className="mt-0.5 size-4 shrink-0" />
                    <p className="flex-1">{inputError}</p>
                    <button type="button" onClick={() => setInputError(null)} aria-label="닫기" className="text-red-400 hover:text-red-600">
                      <X className="size-4" />
                    </button>
                  </div>
                )}

                {!inputError && apiError && (
                  <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                    <CircleAlert className="mt-0.5 size-4 shrink-0" />
                    <p className="flex-1">{apiError.message}</p>
                    {apiError.retryable && (
                      <button type="button" onClick={handleRetry} className="shrink-0 text-xs font-semibold text-red-700 underline hover:text-red-900">
                        다시 보내기
                      </button>
                    )}
                    {needsNewSession && (
                      <button type="button" onClick={restart} className="shrink-0 text-xs font-semibold text-red-700 underline hover:text-red-900">
                        새 상담 시작
                      </button>
                    )}
                  </div>
                )}

                <Composer
                  step={step}
                  sending={sending || loading}
                  onSend={handleSend}
                  onError={setInputError}
                  onRestart={restart}
                />
              </div>
            </>
          )}
        </section>

        <aside className="lg:sticky lg:top-6">
          <StatePanel slots={model.slots} askingIntent={askingIntent} lastTurn={lastTurn} />
        </aside>
      </div>
    </>
  )
}