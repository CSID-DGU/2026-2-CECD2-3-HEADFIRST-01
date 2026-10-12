import { ChevronRight } from 'lucide-react'
import { Card } from '@/components/common/Card'
import { PageHeader } from '@/components/common/PageHeader'
import { PIPELINE_STEPS } from '@/constants/pipeline'

const GOALS = [
  'vLLM 기반 Local LLM 모델 서빙 시스템 구축',
  '온톨로지 프롬프트 기반 의도-엔티티 분류 파이프라인 구축',
  '발화 노이즈(간투사·반복·끊김)에 강인한 의도 분류',
  '상담 시나리오 모사 데이터 생성 및 LLM-as-a-Judge 평가',
]

export function AboutPage() {
  return (
    <>
      <PageHeader title="시스템 소개" description="생성형 AI 활용 사용자 의도-엔티티 분류기 구축 PoC" />

      <div className="space-y-6">
        <Card title="실시간 서빙 파이프라인 (음성 입력 버전)">
          <p className="mb-5 text-sm text-slate-500">음성 입력 → 텍스트 변환 → 분류 → 응답</p>
          <ol className="flex flex-col items-stretch gap-2 md:flex-row md:items-center">
            {PIPELINE_STEPS.map((step, i) => (
              <li key={step.stage} className="flex flex-col items-center gap-2 md:flex-1 md:flex-row">
                <div
                  className={[
                    'w-full rounded-xl border px-4 py-4 text-center',
                    step.stage === 'stt'
                      ? 'border-accent-600/30 bg-accent-50'
                      : 'border-brand-600/25 bg-brand-50',
                  ].join(' ')}
                >
                  <step.icon className="mx-auto mb-2 size-5 text-slate-500" />
                  <p className="font-semibold text-slate-900">{step.component}</p>
                  <p className="mt-0.5 text-sm text-slate-600">{step.task}</p>
                </div>
                {i < PIPELINE_STEPS.length - 1 && (
                  <ChevronRight className="size-5 shrink-0 rotate-90 text-slate-400 md:rotate-0" />
                )}
              </li>
            ))}
          </ol>
        </Card>

        <div className="grid gap-6 md:grid-cols-2">
          <Card title="프로젝트 목표">
            <ul className="space-y-2 text-sm text-slate-700">
              {GOALS.map((g) => (
                <li key={g} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand-500" />
                  {g}
                </li>
              ))}
            </ul>
          </Card>

          <Card title="프로젝트 정보">
            <dl className="grid grid-cols-[88px_1fr] gap-y-2 text-sm">
              <dt className="text-slate-500">협력 기관</dt>
              <dd className="text-slate-800">㈜에이아이웍스</dd>
              <dt className="text-slate-500">과목</dt>
              <dd className="text-slate-800">종합설계2</dd>
              <dt className="text-slate-500">팀</dt>
              <dd className="text-slate-800">맨땅에헤딩</dd>
              <dt className="text-slate-500">팀원</dt>
              <dd className="text-slate-800">손승현, 김천일, 조수현, 강채연</dd>
            </dl>
          </Card>
        </div>
      </div>
    </>
  )
}
