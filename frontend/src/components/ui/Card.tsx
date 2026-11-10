import { clsx } from 'clsx'
import { ReactNode } from 'react'

interface Props {
  children: ReactNode
  className?: string
  title?: string
  actions?: ReactNode
}

export function Card({ children, className, title, actions }: Props) {
  return (
    <div className={clsx('bg-[#13131f] border border-[#1e1e2e] rounded-lg', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e2e]">
          {title && <span className="text-sm font-medium text-slate-300">{title}</span>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}
