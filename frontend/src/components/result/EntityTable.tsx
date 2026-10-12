import { Tags } from 'lucide-react'
import { Card } from '@/components/common/Card'
import type { Entity } from '@/types/classify'
import type { EntityColor } from '@/utils/entityColors'

type Props = {
  entities: Entity[]
  colors: Map<string, EntityColor>
}

export function EntityTable({ entities, colors }: Props) {
  return (
    <Card
      title="엔티티"
      icon={<Tags className="size-4" />}
      actions={<span className="text-xs text-slate-400">{entities.length}개</span>}
    >
      {entities.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">추출된 엔티티가 없습니다.</p>
      ) : (
        <div className="-mx-2 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-500">
                <th className="px-2 py-2 font-medium">#</th>
                <th className="px-2 py-2 font-medium">유형</th>
                <th className="px-2 py-2 font-medium">값</th>
                <th className="hidden px-2 py-2 text-right font-medium sm:table-cell">위치</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((e, i) => (
                <tr key={`${e.type}-${e.value}-${i}`} className="border-b border-slate-50 last:border-0">
                  <td className="px-2 py-2.5 text-slate-400 tabular-nums">{i + 1}</td>
                  <td className="px-2 py-2.5">
                    <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${colors.get(e.type)?.chip ?? ''}`}>
                      {e.type}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 font-medium text-slate-900">{e.value}</td>
                  <td className="hidden px-2 py-2.5 text-right text-xs text-slate-400 tabular-nums sm:table-cell">
                    {e.start != null && e.end != null ? `${e.start}–${e.end}` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
