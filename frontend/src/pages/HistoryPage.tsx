import { PageHeader } from '@/components/common/PageHeader'
import { Placeholder } from '@/components/common/Placeholder'

export function HistoryPage() {
  return (
    <>
      <PageHeader title="분류 기록" description="지금까지 요청한 음성 분류 결과를 모아 봅니다." />
      <Placeholder
        description="백엔드에 기록 저장 API가 생기면 연결합니다."
        plannedFeatures={[
          '분류 요청 목록 (시간·파일명·의도·확신도)',
          '의도 라벨 / 기간으로 필터링',
          '항목 클릭 시 상세 결과 보기',
          '음성 다시 듣기',
        ]}
      />
    </>
  )
}
