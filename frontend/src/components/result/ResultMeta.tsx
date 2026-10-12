import { useState } from 'react'
import { Braces, Check, Copy, Timer } from 'lucide-react'
import { Card } from '@/components/common/Card'
import type { ClassifyResponse } from '@/types/classify'

/** 요청 ID, 처리 시간, 원본 JSON (백엔드 연동 디버깅용) */
export function ResultMeta({ result }: { result: ClassifyResponse }) {
  const [showJson, setShowJson] = useState(false)
  const [copied, setCopied] = useState(false)
  const json = JSON.stringify(result, null, 2)
  const { latencyMs } = result

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* 클립보드 권한이 없으면 무시 */
    }
  }

  const rows: [string, string][] = [
    ['요청 ID', result.requestId],
    ['STT', latencyMs?.stt != null ? `${latencyMs.stt} ms` : '-'],
    ['추론', latencyMs?.inference != null ? `${latencyMs.inference} ms` : '-'],
    ['전체', latencyMs?.total != null ? `${latencyMs.total} ms` : '-'],
  ]

  return (
    <Card
      title="처리 정보"
      icon={<Timer className="size-4" />}
      actions={
        <button
          type="button"
          onClick={() => setShowJson((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800"
        >
          <Braces className="size-3.5" />
          {showJson ? 'JSON 닫기' : 'JSON 보기'}
        </button>
      }
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-xs text-slate-500">{k}</dt>
            <dd className="mt-0.5 truncate font-medium tabular-nums text-slate-800" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>

      {showJson && (
        <div className="relative mt-4">
          <button
            type="button"
            onClick={copy}
            className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-600"
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? '복사됨' : '복사'}
          </button>
          <pre className="max-h-80 overflow-auto rounded-xl bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">
            {json}
          </pre>
        </div>
      )}
    </Card>
  )
}
