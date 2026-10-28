import { CircleHelp, PencilLine } from 'lucide-react'
import { INTENT_MAP } from '@/constants/ontology'
import type { Frame, IntentKey, SlotChange } from '@/types/dialog'
import { formatFrameValue } from '@/utils/dialogState'

type Props = {
  frames: Frame[]
  askedIntent: IntentKey | null
  changes: SlotChange[]
}

/** 한 턴의 분류 결과 (의도 · 액션 · 값) */
export function FrameChips({ frames, askedIntent, changes }: Props) {
  if (frames.length === 0) {
    return <p className="text-xs text-slate-400">분류 결과 없음</p>
  }

  return (
    <ul className="flex flex-wrap justify-end gap-1.5">
      {frames.map((frame, i) => {
        const label = INTENT_MAP[frame.intent].label
        const change = changes.find((c) => c.intent === frame.intent)
        const revised = change?.kind === 'revised'
        const extra = askedIntent !== null && frame.intent !== askedIntent

        return (
          <li
            key={`${frame.intent}-${i}`}
            className={[
              'inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-xs',
              frame.action === 'inform'
                ? 'border-brand-200 bg-white text-slate-700'
                : 'border-amber-200 bg-amber-50 text-amber-800',
            ].join(' ')}
          >
            <span
              className={[
                'rounded px-1 py-px text-[10px] font-semibold tracking-wide uppercase',
                frame.action === 'inform' ? 'bg-brand-100 text-brand-700' : 'bg-amber-100 text-amber-700',
              ].join(' ')}
            >
              {frame.action}
            </span>
            <span className="shrink-0 text-slate-500">{label}</span>
            {frame.action === 'inform' ? (
              <span className="truncate font-semibold text-slate-900">
                {revised && (
                  <>
                    <s className="font-normal text-slate-400">{formatFrameValue(frame.intent, change.from)}</s>
                    <span className="mx-1 text-slate-400">→</span>
                  </>
                )}
                {formatFrameValue(frame.intent, frame.value)}
              </span>
            ) : (
              <span className="inline-flex items-center gap-0.5 font-medium">
                <CircleHelp className="size-3" />
                특정 불가
              </span>
            )}
            {revised && (
              <span className="inline-flex items-center gap-0.5 rounded bg-violet-50 px-1 py-px text-[10px] font-semibold text-violet-700">
                <PencilLine className="size-2.5" />
                정정
              </span>
            )}
            {extra && (
              <span className="rounded bg-slate-100 px-1 py-px text-[10px] font-medium text-slate-500">질문 외</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
