import type { MouseEvent } from 'react'

type Props = {
  peaks: number[] | null
  /** 재생 진행률 0 ~ 1 */
  progress: number
  onSeek?: (ratio: number) => void
  error?: boolean
}

/** 파형 막대 + 재생 위치 표시. 클릭하면 해당 위치로 이동 */
export function Waveform({ peaks, progress, onSeek, error }: Props) {
  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    onSeek?.(Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)))
  }

  // 파형을 못 그리는 경우: 단순 진행 막대
  if (error || !peaks) {
    return (
      <div className="flex h-16 flex-col justify-center gap-2">
        <div className="relative h-1.5 cursor-pointer rounded-full bg-slate-200" onClick={handleClick}>
          <div className="absolute inset-y-0 left-0 rounded-full bg-brand-600" style={{ width: `${progress * 100}%` }} />
        </div>
        <p className="text-center text-xs text-slate-400">{error ? '이 형식은 파형을 표시할 수 없습니다' : '파형 불러오는 중…'}</p>
      </div>
    )
  }

  const playedBars = Math.round(progress * peaks.length)

  return (
    <div
      className="flex h-16 cursor-pointer items-center"
      onClick={handleClick}
      role="slider"
      aria-label="재생 위치"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
    >
      {/* 칸(flex-1) 안에 막대를 60% 너비로 그려서 화면 폭과 상관없이 간격 유지 */}
      {peaks.map((p, i) => (
        <span key={i} className="flex h-full flex-1 items-center justify-center">
          <span
            className={`w-3/5 min-w-px rounded-full transition-colors ${i < playedBars ? 'bg-brand-600' : 'bg-slate-300'}`}
            style={{ height: `${Math.max(6, p * 100)}%` }}
          />
        </span>
      ))}
    </div>
  )
}
