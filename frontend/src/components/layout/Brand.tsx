import { AudioLines } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid size-9 place-items-center rounded-xl bg-brand-700 text-white">
        <AudioLines className="size-5" />
      </span>
      <span className="leading-tight">
        <span className="block text-[15px] font-bold text-slate-900">의도-엔티티 분류기</span>
        {!compact && <span className="block text-xs text-slate-500">PoC · 맨땅에헤딩</span>}
      </span>
    </Link>
  )
}
