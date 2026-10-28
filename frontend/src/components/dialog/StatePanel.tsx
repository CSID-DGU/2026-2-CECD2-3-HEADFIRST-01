import { ClipboardList } from 'lucide-react'
import { Card } from '@/components/common/Card'
import { INTENTS } from '@/constants/ontology'
import type { DialogSlots, IntentKey, Turn } from '@/types/dialog'
import { countFilled } from '@/utils/dialogState'
import { SlotRow } from './SlotRow'

type Props = {
  slots: DialogSlots
  askingIntent: IntentKey | null
  lastTurn: Turn | undefined
}

/** 지금까지 받은 접수 정보 (턴마다 누적·정정) */
export function StatePanel({ slots, askingIntent, lastTurn }: Props) {
  const filled = countFilled(slots)
  const changed = new Set(lastTurn?.changes.map((c) => c.intent))

  return (
    <Card
      title="접수 상태"
      icon={<ClipboardList className="size-4" />}
      actions={
        <span className="text-xs font-medium tabular-nums text-slate-500">
          {filled} / {INTENTS.length}
        </span>
      }
    >
      <div className="-mt-1 mb-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-brand-600 transition-[width] duration-500"
          style={{ width: `${(filled / INTENTS.length) * 100}%` }}
        />
      </div>
      <ul className="-mx-3 space-y-0.5">
        {INTENTS.map((def) => (
          <SlotRow
            key={def.key}
            def={def}
            slot={slots[def.key]}
            asking={askingIntent === def.key}
            justChanged={changed.has(def.key)}
          />
        ))}
      </ul>
    </Card>
  )
}
