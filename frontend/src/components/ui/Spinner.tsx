import { clsx } from 'clsx'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={clsx(
        'inline-block rounded-full border-2 border-indigo-500 border-t-transparent animate-spin',
        className ?? 'w-4 h-4'
      )}
    />
  )
}
