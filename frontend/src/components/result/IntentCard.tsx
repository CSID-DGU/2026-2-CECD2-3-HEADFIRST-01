import { Target } from 'lucide-react'
import { Card } from '@/components/common/Card'
import type { Intent } from '@/types/classify'
import { formatPercent } from '@/utils/format'

type Props = {
  intent: Intent
  candidates?: Intent[]
}

function confidenceTone(c: number) {
  if (c >= 0.8) return { bar: 'bg-brand-600', text: 'text-brand-700', label: '높음' }
  if (c >= 0.5) return { bar: 'bg-amber-500', text: 'text-amber-700', label: '보통' }
  return { bar: 'bg-red-500', text: 'text-red-600', label: '낮음' }
}

export function IntentCard({ intent, candidates = [] }: Props) {
  const tone = confidenceTone(intent.confidence)
  const others = candidates.filter((c) => c.label !== intent.label)

  return (
    <Card title="의도" icon={<Target className="size-4" />} className="h-full">
      <p className="break-all text-2xl font-bold text-slate-900">{intent.label}</p>

      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="text-slate-500">확신도</span>
          <span className={`font-semibold ${tone.text}`}>
            {formatPercent(intent.confidence)} · {tone.label}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full ${tone.bar}`} style={{ width: formatPercent(intent.confidence) }} />
        </div>
      </div>

      {others.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="mb-2 text-xs font-medium text-slate-500">다른 후보</p>
          <ul className="space-y-2">
            {others.map((c) => (
              <li key={c.label} className="flex items-center gap-3 text-sm">
                <span className="w-28 truncate text-slate-700" title={c.label}>
                  {c.label}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-slate-400" style={{ width: formatPercent(c.confidence) }} />
                </div>
                <span className="w-9 text-right text-xs tabular-nums text-slate-500">{formatPercent(c.confidence)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
