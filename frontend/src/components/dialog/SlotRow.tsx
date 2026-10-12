import { Check, CircleDashed, CircleHelp, CircleDot } from 'lucide-react'
import type { IntentDef } from '@/constants/ontology'
import type { SlotState, SlotStatus } from '@/types/dialog'
import { formatFrameValue } from '@/utils/dialogState'

type Props = {
  def: IntentDef
  slot: SlotState
  /** 지금 AI가 묻고 있는 항목 */
  asking: boolean
  /** 직전 턴에서 바뀐 항목 */
  justChanged: boolean
}

const STATUS_STYLE: Record<SlotStatus, { label: string; className: string; icon: typeof Check }> = {
  empty: { label: '대기', className: 'bg-slate-100 text-slate-400', icon: CircleDashed },
  filled: { label: '확정', className: 'bg-brand-100 text-brand-700', icon: Check },
  partial: { label: '일부', className: 'bg-sky-50 text-sky-700', icon: CircleDot },
  uncertain: { label: '불확실', className: 'bg-amber-50 text-amber-700', icon: CircleHelp },
}

/** 접수 항목 한 줄: 이름 · 상태 · 현재 값 · 정정 이력 */
export function SlotRow({ def, slot, asking, justChanged }: Props) {
  const style = STATUS_STYLE[slot.status]
  const Icon = style.icon

  return (
    <li
      // 바뀔 때마다 key 가 달라져 강조 애니메이션이 다시 재생됨
      key={justChanged ? `changed-${slot.updatedTurn}` : 'static'}
      className={[
        'rounded-xl px-3 py-2.5',
        asking ? 'bg-brand-50/60 ring-1 ring-brand-500/60' : '',
        justChanged ? 'animate-flash' : '',
      ].join(' ')}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
          {def.label}
          {asking && <span className="rounded bg-brand-600 px-1.5 py-px text-[10px] font-semibold text-white">질문 중</span>}
        </span>
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}>
          <Icon className="size-3" />
          {style.label}
        </span>
      </div>

      <p
        className={[
          'mt-1 text-sm break-all',
          slot.value === null ? 'text-slate-300' : 'font-semibold text-slate-900 tabular-nums',
        ].join(' ')}
      >
        {formatFrameValue(def.key, slot.value)}
      </p>

      {slot.previous.length > 0 && (
        <p className="mt-0.5 text-xs text-slate-400">
          정정 전{' '}
          {slot.previous.map((p, i) => (
            <span key={i}>
              {i > 0 && ', '}
              <s>{formatFrameValue(def.key, p.value)}</s>
              <span className="ml-0.5">({p.turn}턴)</span>
            </span>
          ))}
        </p>
      )}
    </li>
  )
}
