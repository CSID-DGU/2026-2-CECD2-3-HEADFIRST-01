/**
 * 엔티티 유형별 색상
 * (Tailwind 는 소스에 적힌 클래스만 만들기 때문에 클래스 이름을 문자열 그대로 적어둠)
 */
const PALETTE = [
  { chip: 'bg-teal-100 text-teal-800', mark: 'bg-teal-100 text-teal-900 ring-teal-300' },
  { chip: 'bg-amber-100 text-amber-800', mark: 'bg-amber-100 text-amber-900 ring-amber-300' },
  { chip: 'bg-violet-100 text-violet-800', mark: 'bg-violet-100 text-violet-900 ring-violet-300' },
  { chip: 'bg-sky-100 text-sky-800', mark: 'bg-sky-100 text-sky-900 ring-sky-300' },
  { chip: 'bg-rose-100 text-rose-800', mark: 'bg-rose-100 text-rose-900 ring-rose-300' },
  { chip: 'bg-lime-100 text-lime-800', mark: 'bg-lime-100 text-lime-900 ring-lime-300' },
] as const

export type EntityColor = (typeof PALETTE)[number]

/** 등장 순서대로 유형마다 색을 배정 */
export function buildEntityColorMap(types: string[]): Map<string, EntityColor> {
  const map = new Map<string, EntityColor>()
  for (const t of types) {
    if (!map.has(t)) map.set(t, PALETTE[map.size % PALETTE.length])
  }
  return map
}
