import { ArrowDown, MessageSquareText } from 'lucide-react'
import { Card } from '@/components/common/Card'
import type { Entity } from '@/types/classify'
import type { EntityColor } from '@/utils/entityColors'
import { HighlightedText } from './HighlightedText'

type Props = {
  transcript: string
  normalizedText?: string
  entities: Entity[]
  colors: Map<string, EntityColor>
}

/** STT 원문 → 노이즈 제거 문장 (엔티티 강조) */
export function TranscriptCard({ transcript, normalizedText, entities, colors }: Props) {
  const hasNormalized = !!normalizedText && normalizedText !== transcript

  return (
    <Card title="발화" icon={<MessageSquareText className="size-4" />} className="h-full">
      <div>
        <p className="mb-1.5 text-xs font-medium text-slate-500">STT 변환 원문</p>
        <p className="rounded-lg bg-slate-50 px-3 py-2.5 text-sm leading-relaxed text-slate-600">{transcript}</p>
      </div>

      {hasNormalized && (
        <>
          <div className="my-2 flex items-center gap-2 pl-3 text-xs text-slate-400">
            <ArrowDown className="size-3.5" />
            발화 노이즈 제거
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-slate-500">정제된 발화</p>
            <HighlightedText text={normalizedText} entities={entities} colors={colors} />
          </div>
        </>
      )}

      {!hasNormalized && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-medium text-slate-500">엔티티 표시</p>
          <HighlightedText text={transcript} entities={entities} colors={colors} />
        </div>
      )}
    </Card>
  )
}
