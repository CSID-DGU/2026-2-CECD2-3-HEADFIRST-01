import { useRef } from 'react'
import { CircleAlert, FileAudio, LoaderCircle, Mic, Send, X } from 'lucide-react'
import { ACCEPTED_AUDIO_EXTENSIONS } from '@/config'
import { useRecorder } from '@/hooks/useRecorder'
import { formatDuration } from '@/utils/format'
import { validateAudioFile } from '@/utils/validateAudio'

type Props = {
  onSend: (file: File) => void
  onError: (message: string) => void
  disabled: boolean
}

const ACCEPT_ATTR = [...ACCEPTED_AUDIO_EXTENSIONS, 'audio/*'].join(',')
const LEVEL_BARS = 5

/** 마이크 녹음(누르고 말한 뒤 다시 누르면 전송) + 음성 파일로 보내기 */
export function VoiceInput({ onSend, onError, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const { status, elapsed, level, maxSeconds, start, stop, cancel, dismissError } = useRecorder({ onComplete: onSend })
  const recording = status.state === 'recording'
  const requesting = status.state === 'requesting'

  const handleFile = (file: File | undefined) => {
    if (!file) return
    const message = validateAudioFile(file)
    if (message) onError(message)
    else onSend(file)
  }

  return (
    <div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={recording ? stop : start}
          disabled={disabled || requesting}
          aria-label={recording ? '녹음 끝내고 보내기' : '녹음 시작'}
          className={[
            'relative grid size-12 shrink-0 place-items-center rounded-full text-white shadow-sm transition-colors',
            'disabled:cursor-not-allowed disabled:bg-slate-300',
            recording ? 'bg-red-500 hover:bg-red-600' : 'bg-brand-700 hover:bg-brand-800',
          ].join(' ')}
        >
          {recording && <span className="absolute inset-0 animate-ping rounded-full bg-red-400/40" />}
          {requesting ? (
            <LoaderCircle className="size-5 animate-spin" />
          ) : recording ? (
            <Send className="relative size-5" />
          ) : (
            <Mic className="size-5" />
          )}
        </button>

        <div className="min-w-0 flex-1">
          {recording ? (
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold tabular-nums text-red-600">
                {formatDuration(elapsed)} <span className="font-normal text-slate-400">/ {formatDuration(maxSeconds)}</span>
              </span>
              {/* 입력 크기 표시 */}
              <span className="flex h-5 items-end gap-0.5" aria-hidden>
                {Array.from({ length: LEVEL_BARS }, (_, i) => (
                  <span
                    key={i}
                    className={`w-1 rounded-full transition-[height] ${level * LEVEL_BARS > i ? 'bg-red-500' : 'bg-slate-200'}`}
                    style={{ height: `${30 + i * 17}%` }}
                  />
                ))}
              </span>
              <span className="hidden text-xs text-slate-500 sm:inline">말씀을 마치면 버튼을 다시 누르세요</span>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              {requesting ? '마이크 권한을 확인하는 중…' : '버튼을 누르고 답변을 말해 보세요.'}
            </p>
          )}
        </div>

        {recording ? (
          <button
            type="button"
            onClick={cancel}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          >
            <X className="size-4" />
            취소
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled || requesting}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FileAudio className="size-4" />
            <span className="hidden sm:inline">파일로 보내기</span>
          </button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="hidden"
          onChange={(e) => {
            handleFile(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </div>

      {status.state === 'error' && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-red-600" role="alert">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <span className="flex-1">{status.message}</span>
          <button type="button" onClick={dismissError} className="text-xs text-red-400 hover:text-red-600">
            닫기
          </button>
        </p>
      )}
    </div>
  )
}
