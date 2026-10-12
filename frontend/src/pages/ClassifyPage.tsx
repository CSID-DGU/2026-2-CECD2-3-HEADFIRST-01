import { CircleAlert, Info, LoaderCircle, Mic, RotateCcw, Sparkles, Square } from 'lucide-react'
import { AudioDropzone } from '@/components/audio/AudioDropzone'
import { AudioPreview } from '@/components/audio/AudioPreview'
import { Card } from '@/components/common/Card'
import { PageHeader } from '@/components/common/PageHeader'
import { PipelineStatus } from '@/components/pipeline/PipelineStatus'
import { ResultPanel } from '@/components/result/ResultPanel'
import { config } from '@/config'
import { useAudioFile } from '@/hooks/useAudioFile'
import { useClassify } from '@/hooks/useClassify'

export function ClassifyPage() {
  const { audio, error: fileError, select, clear } = useAudioFile()
  const { status, run, cancel, reset } = useClassify()
  const running = status.state === 'running'

  // 새 파일을 고르면 이전 결과는 지움
  const handleSelect = (file: File) => {
    if (select(file)) reset()
  }

  const handleRemove = () => {
    clear()
    reset()
  }

  return (
    <>
      <PageHeader
        title="단일 발화 분류"
        description="음성 파일을 올리면 발화를 텍스트로 변환하고, 노이즈를 걸러 의도와 엔티티를 분류합니다."
      />

      {config.useMock && (
        <div className="mb-6 flex gap-2.5 rounded-xl border border-accent-600/20 bg-accent-50 px-4 py-3 text-sm text-accent-600">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p>
            <b className="font-semibold">Mock 모드</b> — 백엔드 없이 동작 중이라 음성 내용과 관계없이 샘플 결과가
            표시됩니다.
          </p>
        </div>
      )}

      <div className="space-y-6">
        {/* 1. 음성 입력 */}
        <Card title="음성 입력" icon={<Mic className="size-4" />}>
          {audio ? (
            <AudioPreview
              key={audio.url} // 파일이 바뀌면 플레이어 상태 초기화
              audio={audio}
              onReplace={handleSelect}
              onRemove={handleRemove}
              disabled={running}
            />
          ) : (
            <AudioDropzone onSelect={handleSelect} />
          )}

          {fileError && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-red-600" role="alert">
              <CircleAlert className="size-4 shrink-0" />
              {fileError}
            </p>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            {status.state === 'success' && (
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                <RotateCcw className="size-4" />
                결과 지우기
              </button>
            )}
            {running ? (
              <button
                type="button"
                onClick={cancel}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                <Square className="size-3.5 fill-current" />
                취소
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => audio && run(audio.file)}
              disabled={!audio || running}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {running ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {running ? '분류 중…' : status.state === 'success' ? '다시 분류' : '분류 실행'}
            </button>
          </div>
        </Card>

        {/* 2. 처리 진행 상황 */}
        {status.state !== 'idle' && (
          <div aria-live="polite">
            <PipelineStatus status={status} />
          </div>
        )}

        {/* 3. 결과 */}
        {status.state === 'error' && (
          <div className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-5" role="alert">
            <CircleAlert className="mt-0.5 size-5 shrink-0 text-red-500" />
            <div>
              <p className="font-semibold text-red-700">분류에 실패했습니다</p>
              <p className="mt-1 text-sm text-red-600">{status.message}</p>
            </div>
          </div>
        )}

        {status.state === 'success' && <ResultPanel result={status.result} />}

        {status.state === 'idle' && (
          <div className="rounded-2xl border border-dashed border-slate-200 py-12 text-center text-sm text-slate-400">
            {audio ? '‘분류 실행’을 누르면 결과가 여기에 표시됩니다.' : '음성 파일을 먼저 올려주세요.'}
          </div>
        )}
      </div>
    </>
  )
}
