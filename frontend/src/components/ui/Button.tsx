import { clsx } from 'clsx'
import { ReactNode, ButtonHTMLAttributes } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  children: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  children,
  className,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center gap-2 font-mono font-medium transition-all rounded',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        {
          'bg-indigo-600 hover:bg-indigo-500 text-white': variant === 'primary',
          'bg-transparent hover:bg-white/5 text-slate-300 border border-slate-700': variant === 'ghost',
          'bg-transparent hover:bg-white/5 text-slate-300 border border-slate-600': variant === 'outline',
          'bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-800': variant === 'danger',
          'text-xs px-2 py-1': size === 'sm',
          'text-sm px-3 py-1.5': size === 'md',
          'text-base px-4 py-2': size === 'lg',
        },
        className
      )}
    >
      {loading && (
        <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  )
}
