import { useRef, useState } from 'react'
import { SendHorizontal } from 'lucide-react'
import type { IntentDef } from '@/constants/ontology'

type Props = {
  onSend: (text: string) => void
  disabled: boolean
  /** 지금 묻는 항목 (예시 발화 표시용) */
  askingDef: IntentDef | null
}

/** STT 없이 발화를 직접 입력 (분류기만 테스트할 때) */
export function TextInput({ onSend, disabled, askingDef }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const canSend = !disabled && text.trim().length > 0

  const submit = () => {
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  return (
    <div>
      <div className="flex gap-2">
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // 한글 조합 중 Enter 는 무시 (조합 완료 후 한 번만 전송되도록)
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
          disabled={disabled}
          placeholder="민원인 발화를 입력하세요"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-[15px] placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none disabled:bg-slate-50"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <SendHorizontal className="size-4" />
          보내기
        </button>
      </div>

      {askingDef && askingDef.examples.length > 0 && (
        <div className="mt-2.5">
          <p className="mb-1.5 text-xs text-slate-400">온톨로지 예시 발화 · 누르면 입력창에 채워져요</p>
          {/* 질문이 바뀌면 가로 스크롤 위치도 처음으로 */}
          <ul key={askingDef.key} className="flex gap-1.5 overflow-x-auto pb-1">
            {askingDef.examples.map((ex) => (
              <li key={ex.utterance} className="shrink-0">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    setText(ex.utterance)
                    inputRef.current?.focus()
                  }}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 hover:border-brand-500/50 hover:bg-brand-50 hover:text-brand-800 disabled:opacity-50"
                >
                  {ex.utterance}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
