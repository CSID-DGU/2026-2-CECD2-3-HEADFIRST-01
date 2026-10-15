import type { ReactNode } from 'react'

type Props = {
  title?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  className?: string
  children: ReactNode
}

export function Card({ title, icon, actions, className = '', children }: Props) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
            {icon && <span className="text-brand-600">{icon}</span>}
            {title}
          </h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}
