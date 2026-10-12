import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return (
    <input
      data-slot="input"
      className={cn(
        'flex h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 text-base transition-colors outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}
