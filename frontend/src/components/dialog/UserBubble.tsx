import { useState } from 'react'
import { Braces, Keyboard, Mic } from 'lucide-react'
import type { Turn } from '@/types/dialog'
import { AudioReplayButton } from './AudioReplayButton'
import { FrameChips } from './FrameChips'

/** 민원인 말풍선 (오른쪽) + 이번 턴 분류 결과 */
export function UserBubble({ turn }: { turn: Turn }) {
  const [showJson, setShowJson] = useState(false)
  const InputIcon = turn.input === 'voice' ? Mic : Keyboard
  const total = turn.latencyMs?.total

  return (
    <div className="flex flex-col items-end gap-1.5">
      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        <InputIcon className="size-3" />
        민원인 · {turn.index}번째 응답
        {turn.audioUrl && <AudioReplayButton src={turn.audioUrl} />}
      </p>
      <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-700 px-4 py-2.5 text-[15px] leading-relaxed text-white">
        {turn.transcript || <span className="opacity-70">(말소리 없음)</span>}
      </div>

      <div className="flex max-w-[92%] flex-col items-end gap-1">
        <FrameChips frames={turn.frames} askedIntent={turn.askedIntent} changes={turn.changes} />
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          {total != null && <span className="tabular-nums">{total} ms</span>}
          {turn.sttEngine && <span>STT {turn.sttEngine}</span>}
          <button
            type="button"
            onClick={() => setShowJson((v) => !v)}
            className="inline-flex items-center gap-0.5 rounded px-1 hover:bg-slate-100 hover:text-slate-600"
          >
            <Braces className="size-3" />
            {showJson ? '닫기' : 'frames'}
          </button>
        </div>
        {showJson && (
          <pre className="max-h-60 w-full overflow-auto rounded-lg bg-slate-900 p-3 text-left text-[11px] leading-relaxed text-slate-100">
            {JSON.stringify({ askedIntent: turn.askedIntent, frames: turn.frames }, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
