import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from '@/routes'

export function NavList({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="space-y-1">
      {NAV_ITEMS.map(({ to, label, icon: Icon, wip }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
              ].join(' ')
            }
          >
            <Icon className="size-[18px]" />
            <span className="flex-1">{label}</span>
            {wip && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">준비 중</span>}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}
