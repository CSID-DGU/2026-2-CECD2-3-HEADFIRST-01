import type { ReactNode } from 'react'
import type { Entity } from '@/types/classify'
import type { EntityColor } from '@/utils/entityColors'

type Props = {
  text: string
  entities: Entity[]
  colors: Map<string, EntityColor>
}

type Span = { start: number; end: number; entity: Entity }

/** start/end 가 틀렸거나 없으면 문자열 검색으로 위치를 찾는다 */
function resolveSpans(text: string, entities: Entity[]): Span[] {
  const spans: Span[] = []
  for (const entity of entities) {
    let { start, end } = entity
    if (start == null || end == null || text.slice(start, end) !== entity.value) {
      start = text.indexOf(entity.value)
      end = start + entity.value.length
    }
    if (start >= 0) spans.push({ start, end: end!, entity })
  }
  // 앞에서부터 정렬 후 겹치는 구간 제거
  spans.sort((a, b) => a.start - b.start)
  const result: Span[] = []
  for (const s of spans) {
    const prev = result[result.length - 1]
    if (!prev || s.start >= prev.end) result.push(s)
  }
  return result
}

/** 문장 안의 엔티티를 색으로 강조 */
export function HighlightedText({ text, entities, colors }: Props) {
  const spans = resolveSpans(text, entities)
  const parts: ReactNode[] = []
  let cursor = 0

  spans.forEach((s, i) => {
    if (s.start > cursor) parts.push(text.slice(cursor, s.start))
    const color = colors.get(s.entity.type)
    parts.push(
      <mark
        key={i}
        title={s.entity.type}
        className={`rounded px-1 py-0.5 ring-1 ring-inset ${color?.mark ?? 'bg-slate-100'}`}
      >
        {text.slice(s.start, s.end)}
        <sub className="ml-0.5 align-baseline text-[10px] font-semibold opacity-70">{s.entity.type}</sub>
      </mark>,
    )
    cursor = s.end
  })
  if (cursor < text.length) parts.push(text.slice(cursor))

  return <p className="text-[17px] leading-9 text-slate-900">{parts}</p>
}
