import { Check, LoaderCircle, X } from 'lucide-react'
import { PIPELINE_STEPS } from '@/constants/pipeline'
import type { ClassifyStatus } from '@/types/classify'

type StepState = 'pending' | 'active' | 'done' | 'error'

function getStepStates(status: ClassifyStatus): StepState[] {
  const n = PIPELINE_STEPS.length
  if (status.state === 'idle') return Array(n).fill('pending')
  if (status.state === 'success') return Array(n).fill('done')

  const current = PIPELINE_STEPS.findIndex((s) => s.stage === status.stage)
  const activeState: StepState = status.state === 'error' ? 'error' : 'active'
  return PIPELINE_STEPS.map((_, i) => (i < current ? 'done' : i === current ? activeState : 'pending'))
}

/** 업로드 → STT → 파싱 → 추론 진행 상황 */
export function PipelineStatus({ status }: { status: ClassifyStatus }) {
  const states = getStepStates(status)

  return (
    <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {PIPELINE_STEPS.map((step, i) => {
        const state = states[i]
        return (
          <li
            key={step.stage}
            className={[
              'relative flex items-center gap-3 rounded-xl border px-3 py-3 transition-colors',
              state === 'active' && 'border-brand-500 bg-brand-50',
              state === 'done' && 'border-brand-200 bg-white',
              state === 'error' && 'border-red-300 bg-red-50',
              state === 'pending' && 'border-slate-200 bg-white',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span
              className={[
                'grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold',
                state === 'active' && 'bg-brand-600 text-white',
                state === 'done' && 'bg-brand-100 text-brand-700',
                state === 'error' && 'bg-red-500 text-white',
                state === 'pending' && 'bg-slate-100 text-slate-400',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {state === 'active' ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : state === 'done' ? (
                <Check className="size-4" />
              ) : state === 'error' ? (
                <X className="size-4" />
              ) : (
                i + 1
              )}
            </span>
            <div className="min-w-0">
              <p className={`text-sm leading-snug font-medium ${state === 'pending' ? 'text-slate-400' : 'text-slate-900'}`}>
                {step.progressLabel}
              </p>
              <p className="truncate text-xs text-slate-500">{step.component}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
