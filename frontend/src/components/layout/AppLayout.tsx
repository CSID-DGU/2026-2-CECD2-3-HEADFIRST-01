import { useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { Brand } from './Brand'
import { NavList } from './NavList'
import { ModeBadge } from './ModeBadge'

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="min-h-dvh lg:flex">
      {/* 데스크톱 사이드바 */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <div className="px-5 py-6">
          <Brand />
        </div>
        <nav className="flex-1 px-3">
          <NavList />
        </nav>
        <div className="space-y-2 border-t border-slate-100 px-5 py-4">
          <ModeBadge />
          <p className="text-xs text-slate-400">㈜에이아이웍스 산학협력 · 종합설계2</p>
        </div>
      </aside>

      {/* 모바일 상단바 */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur lg:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <Brand compact />
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
            aria-label={mobileOpen ? '메뉴 닫기' : '메뉴 열기'}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
        {mobileOpen && (
          <nav className="space-y-3 border-t border-slate-100 px-3 py-3">
            {/* 메뉴를 누르면 닫기 */}
            <NavList onNavigate={() => setMobileOpen(false)} />
            <div className="px-2">
              <ModeBadge />
            </div>
          </nav>
        )}
      </header>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
