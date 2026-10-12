import { useEffect, useRef, useState } from 'react'
import { FileAudio, Pause, Play, RefreshCw, Trash2 } from 'lucide-react'
import { ACCEPTED_AUDIO_EXTENSIONS } from '@/config'
import type { AudioFileState } from '@/hooks/useAudioFile'
import { useWaveform } from '@/hooks/useWaveform'
import { formatBytes, formatDuration, getExtension } from '@/utils/format'
import { Waveform } from './Waveform'

type Props = {
  audio: AudioFileState
  onReplace: (file: File) => void
  onRemove: () => void
  disabled?: boolean
}

/** 선택한 음성 파일 정보 + 미리듣기 플레이어 */
export function AudioPreview({ audio, onReplace, onRemove, disabled = false }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const { peaks, error } = useWaveform(audio.file)

  const duration = audio.duration ?? 0
  const progress = duration > 0 ? current / duration : 0

  // 재생 중엔 매 프레임 현재 시간 갱신 (파형이 부드럽게 채워지도록)
  useEffect(() => {
    if (!playing) return
    let raf = 0
    const tick = () => {
      setCurrent(audioRef.current?.currentTime ?? 0)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  // 분류가 시작되면(disabled) 재생 정지
  useEffect(() => {
    if (disabled) audioRef.current?.pause()
  }, [disabled])

  const togglePlay = () => {
    const el = audioRef.current
    if (!el) return
    if (el.paused) el.play()
    else el.pause()
  }

  const seek = (ratio: number) => {
    const el = audioRef.current
    if (!el || !duration) return
    el.currentTime = ratio * duration
    setCurrent(el.currentTime)
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
      {/* 파일 정보 */}
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-700">
          <FileAudio className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-slate-900" title={audio.file.name}>
            {audio.file.name}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {getExtension(audio.file.name).slice(1).toUpperCase() || audio.file.type} ·{' '}
            {formatBytes(audio.file.size)} · {formatDuration(audio.duration)}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-white hover:text-slate-900 disabled:opacity-40"
          >
            <RefreshCw className="size-3.5" />
            <span className="hidden sm:inline">다른 파일</span>
          </button>
          <button
            type="button"
            onClick={onRemove}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-white hover:text-red-600 disabled:opacity-40"
          >
            <Trash2 className="size-3.5" />
            <span className="hidden sm:inline">삭제</span>
          </button>
        </div>
      </div>

      {/* 플레이어 */}
      <div className="mt-4 flex items-center gap-3 sm:gap-4">
        <button
          type="button"
          onClick={togglePlay}
          disabled={disabled}
          aria-label={playing ? '일시정지' : '재생'}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-brand-700 text-white shadow-sm hover:bg-brand-800 disabled:opacity-40"
        >
          {playing ? <Pause className="size-5" /> : <Play className="ml-0.5 size-5" />}
        </button>
        <div className="min-w-0 flex-1">
          <Waveform peaks={peaks} error={error} progress={progress} onSeek={seek} />
        </div>
        <span className="w-20 shrink-0 text-right text-xs tabular-nums text-slate-500">
          {formatDuration(current)} / {formatDuration(audio.duration)}
        </span>
      </div>

      <audio
        ref={audioRef}
        src={audio.url}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setCurrent(duration)
        }}
        className="hidden"
      />
      <input
        ref={inputRef}
        type="file"
        accept={[...ACCEPTED_AUDIO_EXTENSIONS, 'audio/*'].join(',')}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onReplace(file)
          e.target.value = ''
        }}
      />
    </div>
  )
}
