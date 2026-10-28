import { useEffect, useRef } from 'react'
import { RotateCw } from 'lucide-react'
import { INTENT_MAP } from '@/constants/ontology'
import type { PendingTurn } from '@/hooks/useDialog'
import type { DialogSlots, Turn } from '@/types/dialog'
import type { NextStep } from '@/utils/nextQuestion'
import { PendingBubble } from './PendingBubble'
import { SummaryBubble } from './SummaryBubble'
import { SystemBubble } from './SystemBubble'
import { UserBubble } from './UserBubble'

type Props = {
  turns: Turn[]
  pending: PendingTurn | null
  step: NextStep
  slots: DialogSlots
  onCancel: () => void
}

function IntentTag({ label, retry }: { label: string; retry?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-px text-[11px] font-medium text-slate-500">
      {retry && <RotateCw className="size-2.5" />}
      {label}
    </span>
  )
}

/** 상담 대화 흐름: (AI 질문 → 민원인 응답) 반복 → 마무리 */
export function ChatTimeline({ turns, pending, step, slots, onCancel, className = '' }: Props & { className?: string }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // 새 말풍선이 생기면 대화창만 맨 아래로 (페이지 전체는 움직이지 않게)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [turns.length, pending?.stage, step.type])

  return (
    <div ref={scrollRef} className={`space-y-5 overflow-y-auto overscroll-contain ${className}`}>
      {turns.map((turn) => (
        <div key={turn.index} className="space-y-4">
          <SystemBubble tag={turn.askedIntent && <IntentTag label={INTENT_MAP[turn.askedIntent].label} />}>
            {turn.question}
          </SystemBubble>
          <UserBubble turn={turn} />
        </div>
      ))}

      {pending ? (
        <div className="space-y-4">
          <SystemBubble tag={pending.askedIntent && <IntentTag label={INTENT_MAP[pending.askedIntent].label} />}>
            {pending.question}
          </SystemBubble>
          <PendingBubble pending={pending} onCancel={onCancel} />
        </div>
      ) : step.type === 'ask' ? (
        <SystemBubble tag={<IntentTag label={INTENT_MAP[step.intent].label} retry={step.retry} />}>
          {step.question}
        </SystemBubble>
      ) : (
        <SummaryBubble reason={step.reason} slots={slots} />
      )}
    </div>
  )
}
