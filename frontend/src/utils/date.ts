/** 로컬 시간 기준 오늘 날짜 YYYY-MM-DD */
export function todayISO(): string {
  return toISODate(new Date())
}

export function toISODate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** YYYY-MM-DD 에 days 만큼 더한 날짜 (음수면 이전 날짜) */
export function shiftISODate(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return toISODate(new Date(y, m - 1, d + days))
}

/** 두 YYYY-MM-DD 사이 일수 (b - a) */
export function diffISODays(a: string, b: string): number {
  const toTime = (iso: string) => {
    const [y, m, d] = iso.split('-').map(Number)
    return new Date(y, m - 1, d).getTime()
  }
  return Math.round((toTime(b) - toTime(a)) / 86_400_000)
}

/** "2026-10-12" → "2026년 10월 12일" */
export function formatKoreanDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${y}년 ${Number(m)}월 ${Number(d)}일`
}
