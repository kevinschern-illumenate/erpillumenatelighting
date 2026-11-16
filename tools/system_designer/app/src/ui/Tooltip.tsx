import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import type { ReactElement, ReactNode } from 'react';

/** A hover and focus hint. It never carries the only copy of information: names stay on the control. */
export function Tooltip({
  content,
  children,
  side = 'bottom',
}: {
  content: ReactNode;
  children: ReactElement;
  side?: 'top' | 'bottom' | 'left' | 'right';
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={400} skipDelayDuration={200}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content className="ill-sd-layer sd-tooltip" side={side} sideOffset={6}>
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
