import { useState } from 'react'
import { Keyboard, Mic, RotateCcw } from 'lucide-react'
import type { TurnInput } from '@/api/dialog'
import { INTENT_MAP } from '@/constants/ontology'
import type { NextStep } from '@/utils/nextQuestion'
import { TextInput } from './TextInput'
import { VoiceInput } from './VoiceInput'

type Mode = TurnInput['kind']

type Props = {
  step: NextStep
  sending: boolean
  onSend: (input: TurnInput) => void
  onError: (message: string) => void
  onRestart: () => void
}

const MODES: { mode: Mode; label: string; icon: typeof Mic }[] = [
  { mode: 'voice', label: '음성', icon: Mic },
  { mode: 'text', label: '텍스트', icon: Keyboard },
]

/** 민원인 응답 입력창 (음성 / 텍스트 전환) */
export function Composer({ step, sending, onSend, onError, onRestart }: Props) {
  const [mode, setMode] = useState<Mode>('voice')

  if (step.type === 'done') {
    return (
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-slate-500">상담이 끝났습니다.</p>
        <button
          type="button"
          onClick={onRestart}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-800"
        >
          <RotateCcw className="size-4" />새 상담 시작
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-3 inline-flex rounded-lg bg-slate-100 p-0.5" role="tablist" aria-label="입력 방식">
        {MODES.map(({ mode: m, label, icon: Icon }) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={[
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              mode === m ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
            ].join(' ')}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>

      {mode === 'voice' ? (
        <VoiceInput disabled={sending} onError={onError} onSend={(audio) => onSend({ kind: 'voice', audio })} />
      ) : (
        <TextInput
          disabled={sending}
          askingDef={INTENT_MAP[step.intent]}
          onSend={(text) => onSend({ kind: 'text', text })}
        />
      )}
    </div>
  )
}
