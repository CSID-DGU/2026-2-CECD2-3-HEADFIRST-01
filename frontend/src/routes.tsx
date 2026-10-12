import { AudioLines, History, Scale, Workflow, type LucideIcon } from 'lucide-react'

export type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  /** 아직 기능이 없는 페이지 표시 */
  wip?: boolean
}

/** 사이드바 메뉴 (페이지를 추가하면 여기와 App.tsx 에 등록) */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '분류 데모', icon: AudioLines },
  { to: '/history', label: '분류 기록', icon: History, wip: true },
  { to: '/evaluation', label: '모델 평가', icon: Scale, wip: true },
  { to: '/about', label: '시스템 소개', icon: Workflow },
]
