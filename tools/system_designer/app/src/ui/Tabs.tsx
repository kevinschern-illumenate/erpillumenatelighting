import * as TabsPrimitive from '@radix-ui/react-tabs';
import type { ReactNode } from 'react';
import { cn } from './cn';

export interface TabItem {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

/** Radix Tabs: arrow keys move between tabs, and each panel is labelled by its tab. */
export function Tabs({
  tabs,
  value,
  onValueChange,
  label,
  className,
}: {
  tabs: TabItem[];
  value: string;
  onValueChange(value: string): void;
  label: string;
  className?: string;
}) {
  return (
    <TabsPrimitive.Root className={cn('sd-tabs', className)} value={value} onValueChange={onValueChange}>
      <TabsPrimitive.List className="sd-tabs__list" aria-label={label}>
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger key={tab.id} value={tab.id} className="sd-tabs__tab">
            {tab.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {tabs.map((tab) => (
        <TabsPrimitive.Content key={tab.id} value={tab.id} className="sd-tabs__panel">
          {tab.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
