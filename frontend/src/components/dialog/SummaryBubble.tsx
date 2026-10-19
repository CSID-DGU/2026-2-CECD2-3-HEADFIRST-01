import { CircleCheck, CircleSlash } from 'lucide-react'
import { INTENTS } from '@/constants/ontology'
import type { DialogSlots } from '@/types/dialog'
import { formatFrameValue } from '@/utils/dialogState'
import type { NextStep } from '@/utils/nextQuestion'
import { SystemBubble } from './SystemBubble'

type Props = {
  reason: Extract<NextStep, { type: 'done' }>['reason']
  slots: DialogSlots
}

/** 상담이 끝났을 때 AI 상담원의 마무리 말풍선 */
export function SummaryBubble({ reason, slots }: Props) {
  if (reason === 'no_consent') {
    return (
      <SystemBubble tag={<CircleSlash className="size-3 text-slate-400" />}>
        개인정보 수집에 동의하지 않으셔서 전화 접수는 어렵습니다. 가까운 구청 민원실을 방문해 주세요.
      </SystemBubble>
    )
  }

  return (
    <SystemBubble tag={<CircleCheck className="size-3 text-brand-600" />}>
      <p>말씀하신 내용을 정리해 드릴게요.</p>
      <dl className="mt-2.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-white px-3.5 py-3 text-sm">
        {INTENTS.map((d) => (
          <div key={d.key} className="contents">
            <dt className="text-slate-500">{d.label}</dt>
            <dd className="font-medium text-slate-900">{formatFrameValue(d.key, slots[d.key].value)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2.5">맞으시면 이대로 접수해 드리겠습니다.</p>
    </SystemBubble>
  )
}
