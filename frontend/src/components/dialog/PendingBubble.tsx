import { LoaderCircle, Mic, Square } from 'lucide-react'
import { PIPELINE_STEPS } from '@/constants/pipeline'
import type { PendingTurn } from '@/hooks/useDialog'

/** 보내는 중인 민원인 응답 (처리 단계 표시 + 취소) */
export function PendingBubble({ pending, onCancel }: { pending: PendingTurn; onCancel: () => void }) {
  const steps = PIPELINE_STEPS.filter((s) => (pending.input === 'voice' ? s.stage !== 'parse' : s.stage === 'inference'))
  const current = steps.findIndex((s) => s.stage === pending.stage)

  return (
    <div className="flex flex-col items-end gap-1.5" aria-live="polite">
      <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-700/80 px-4 py-2.5 text-[15px] leading-relaxed text-white">
        {pending.input === 'text' ? (
          pending.text
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <Mic className="size-4" />
            음성 응답
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <ol className="flex items-center gap-1.5">
          {steps.map((s, i) => (
            <li
              key={s.stage}
              className={[
                'inline-flex items-center gap-1 rounded-full px-2 py-0.5',
                i < current && 'bg-brand-50 text-brand-700',
                i === current && 'bg-brand-600 text-white',
                i > current && 'bg-slate-100 text-slate-400',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {i === current && <LoaderCircle className="size-3 animate-spin" />}
              {s.progressLabel}
            </li>
          ))}
        </ol>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800"
        >
          <Square className="size-2.5 fill-current" />
          취소
        </button>
      </div>
    </div>
  )
}
