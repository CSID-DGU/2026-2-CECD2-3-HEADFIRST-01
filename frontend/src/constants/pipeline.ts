import { Braces, CloudUpload, Cpu, FileText, type LucideIcon } from 'lucide-react'
import type { PipelineStage } from '@/types/classify'

export type PipelineStep = {
  stage: PipelineStage
  /** 담당 구성요소 (다이어그램의 박스 이름) */
  component: string
  /** 하는 일 */
  task: string
  /** 진행 표시에 쓰는 짧은 문구 */
  progressLabel: string
  icon: LucideIcon
}

/** 실시간 서빙 파이프라인 (음성 입력 버전) */
export const PIPELINE_STEPS: PipelineStep[] = [
  { stage: 'upload', component: '프론트엔드', task: '음성 입력 UI', progressLabel: '음성 업로드', icon: CloudUpload },
  { stage: 'stt', component: 'STT 변환', task: '음성 → 텍스트', progressLabel: '텍스트 변환', icon: FileText },
  { stage: 'parse', component: '백엔드', task: '프롬프트·파싱', progressLabel: '프롬프트 구성', icon: Braces },
  { stage: 'inference', component: 'AI 서빙', task: 'vLLM 추론', progressLabel: '의도·엔티티 분류', icon: Cpu },
]
