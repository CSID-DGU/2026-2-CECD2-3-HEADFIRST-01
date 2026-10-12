import { Construction } from 'lucide-react'

type Props = {
  title?: string
  description?: string
  /** 앞으로 들어갈 기능 목록 (팀원 참고용) */
  plannedFeatures?: string[]
}

/** 아직 구현되지 않은 페이지에 쓰는 자리 표시 */
export function Placeholder({ title = '준비 중인 페이지입니다', description, plannedFeatures = [] }: Props) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white px-6 py-14 text-center">
      <span className="mx-auto grid size-12 place-items-center rounded-full bg-slate-100 text-slate-400">
        <Construction className="size-6" />
      </span>
      <h2 className="mt-4 text-base font-semibold text-slate-800">{title}</h2>
      {description && <p className="mt-1.5 text-sm text-slate-500">{description}</p>}

      {plannedFeatures.length > 0 && (
        <div className="mx-auto mt-6 max-w-sm rounded-xl bg-slate-50 p-4 text-left">
          <p className="mb-2 text-xs font-semibold text-slate-500">구현 예정</p>
          <ul className="space-y-1.5 text-sm text-slate-600">
            {plannedFeatures.map((f) => (
              <li key={f} className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-slate-400" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
