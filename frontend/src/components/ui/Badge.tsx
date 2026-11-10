import { clsx } from 'clsx'

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'active'

interface Props {
  variant?: Variant
  children: React.ReactNode
  className?: string
}

export function Badge({ variant = 'muted', children, className }: Props) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium',
        {
          'bg-green-500/15 text-green-400': variant === 'success',
          'bg-yellow-500/15 text-yellow-400': variant === 'warning',
          'bg-red-500/15 text-red-400': variant === 'danger',
          'bg-indigo-500/15 text-indigo-400': variant === 'info',
          'bg-white/5 text-slate-400': variant === 'muted',
          'bg-indigo-600 text-white': variant === 'active',
        },
        className
      )}
    >
      {children}
    </span>
  )
}
