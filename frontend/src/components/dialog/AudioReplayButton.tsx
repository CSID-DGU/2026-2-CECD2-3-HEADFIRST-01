import { useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'

/** 녹음한 음성 다시 듣기 (작은 버튼) */
export function AudioReplayButton({ src }: { src: string }) {
  const ref = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)

  const toggle = () => {
    const el = ref.current
    if (!el) return
    if (el.paused) {
      el.currentTime = 0
      el.play().catch(() => setPlaying(false))
    } else el.pause()
  }

  return (
    <>
      <button
        type="button"
        onClick={toggle}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-brand-700 hover:bg-brand-100"
        aria-label={playing ? '정지' : '음성 다시 듣기'}
      >
        {playing ? <Pause className="size-3" /> : <Play className="size-3" />}
        {playing ? '정지' : '듣기'}
      </button>
      <audio
        ref={ref}
        src={src}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
    </>
  )
}
