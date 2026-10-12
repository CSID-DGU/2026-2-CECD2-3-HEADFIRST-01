import { useRef, useState, type DragEvent } from 'react'
import { CloudUpload } from 'lucide-react'
import { ACCEPTED_AUDIO_EXTENSIONS, config } from '@/config'

type Props = {
  onSelect: (file: File) => void
  disabled?: boolean
}

const ACCEPT_ATTR = [...ACCEPTED_AUDIO_EXTENSIONS, 'audio/*'].join(',')

/** 음성 파일 드래그 앤 드롭 + 클릭 선택 영역 */
export function AudioDropzone({ onSelect, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  // 자식 요소 위를 지날 때 dragleave 가 튀는 것 방지
  const dragDepth = useRef(0)

  const openPicker = () => {
    if (!disabled) inputRef.current?.click()
  }

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (file) onSelect(file)
  }

  const onDragEnter = (e: DragEvent) => {
    e.preventDefault()
    if (disabled) return
    dragDepth.current += 1
    setDragging(true)
  }

  const onDragLeave = (e: DragEvent) => {
    e.preventDefault()
    dragDepth.current -= 1
    if (dragDepth.current <= 0) setDragging(false)
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    if (!disabled) handleFiles(e.dataTransfer.files)
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          openPicker()
        }
      }}
      onDragEnter={onDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={[
        'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500',
        dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50/60 hover:border-brand-500/60 hover:bg-brand-50/40',
        disabled ? 'pointer-events-none opacity-50' : '',
      ].join(' ')}
    >
      <span
        className={[
          'grid size-14 place-items-center rounded-full transition-colors',
          dragging ? 'bg-brand-600 text-white' : 'bg-white text-brand-600 shadow-sm ring-1 ring-slate-200',
        ].join(' ')}
      >
        <CloudUpload className="size-7" />
      </span>
      <p className="mt-4 text-[15px] font-semibold text-slate-800">
        {dragging ? '여기에 놓으세요' : '음성 파일을 끌어다 놓거나 클릭해서 선택하세요'}
      </p>
      <p className="mt-1.5 text-xs text-slate-500">
        {ACCEPTED_AUDIO_EXTENSIONS.map((e) => e.slice(1).toUpperCase()).join(' · ')} · 최대 {config.maxUploadMB}MB
      </p>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_ATTR}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files)
          e.target.value = '' // 같은 파일을 다시 선택해도 onChange 가 동작하도록
        }}
      />
    </div>
  )
}
