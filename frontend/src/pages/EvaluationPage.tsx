import { PageHeader } from '@/components/common/PageHeader'
import { Placeholder } from '@/components/common/Placeholder'

export function EvaluationPage() {
  return (
    <>
      <PageHeader title="모델 평가" description="LLM-as-a-Judge 로 분류기 성능을 평가한 결과를 확인합니다." />
      <Placeholder
        description="평가 데이터 형식이 정해지면 구현합니다."
        plannedFeatures={[
          '테스트 시나리오별 의도 분류 정확도',
          '노이즈 유형별(간투사·반복·끊김) 성능 비교',
          'LLM-as-a-Judge 채점 결과 및 근거',
          '모사 데이터셋 목록 관리',
        ]}
      />
    </>
  )
}
