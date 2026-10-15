import { config } from '@/config'

/** 현재 Mock 모드인지 실제 API 모드인지 표시 */
export function ModeBadge() {
  return config.useMock ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-100 px-2.5 py-1 text-xs font-medium text-accent-600">
      <span className="size-1.5 rounded-full bg-accent-600" />
      Mock 모드
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-100 px-2.5 py-1 text-xs font-medium text-brand-700">
      <span className="size-1.5 rounded-full bg-brand-600" />
      API 연결
    </span>
  )
}
