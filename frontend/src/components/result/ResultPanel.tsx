import { useMemo } from 'react'
import type { ClassifyResponse } from '@/types/classify'
import { buildEntityColorMap } from '@/utils/entityColors'
import { EntityTable } from './EntityTable'
import { IntentCard } from './IntentCard'
import { ResultMeta } from './ResultMeta'
import { TranscriptCard } from './TranscriptCard'

/** 분류 결과 전체 */
export function ResultPanel({ result }: { result: ClassifyResponse }) {
  const colors = useMemo(() => buildEntityColorMap(result.entities.map((e) => e.type)), [result.entities])

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <IntentCard intent={result.intent} candidates={result.candidates} />
        </div>
        <div className="lg:col-span-3">
          <TranscriptCard
            transcript={result.transcript}
            normalizedText={result.normalizedText}
            entities={result.entities}
            colors={colors}
          />
        </div>
      </div>
      <EntityTable entities={result.entities} colors={colors} />
      <ResultMeta result={result} />
    </div>
  )
}
