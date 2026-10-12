import type { ReactNode } from 'react'
import { Headset } from 'lucide-react'

type Props = {
  /** 말풍선 위 작은 표시 (예: 묻는 항목 이름) */
  tag?: ReactNode
  children: ReactNode
}

/** AI 상담원 말풍선 (왼쪽) */
export function SystemBubble({ tag, children }: Props) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-5 grid size-8 shrink-0 place-items-center rounded-full bg-brand-700 text-white">
        <Headset className="size-4" />
      </span>
      <div className="min-w-0 max-w-[85%]">
        <p className="mb-1 flex items-center gap-1.5 text-xs text-slate-400">
          AI 상담원
          {tag}
        </p>
        <div className="rounded-2xl rounded-tl-md bg-slate-100 px-4 py-2.5 text-[15px] leading-relaxed text-slate-800">
          {children}
        </div>
      </div>
    </div>
  )
}
