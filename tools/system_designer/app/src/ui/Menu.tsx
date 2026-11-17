import * as MenuPrimitive from '@radix-ui/react-dropdown-menu';
import { Check } from 'lucide-react';
import type { ReactElement, ReactNode } from 'react';
import { Kbd } from './Kbd';

/** A dropdown menu (Radix): arrow keys, type-ahead, Escape and focus return come with it. */
export function Menu({
  trigger,
  children,
  align = 'end',
  label,
}: {
  trigger: ReactElement;
  children: ReactNode;
  align?: 'start' | 'end';
  label?: string;
}) {
  return (
    <MenuPrimitive.Root modal={false}>
      <MenuPrimitive.Trigger asChild>{trigger}</MenuPrimitive.Trigger>
      <MenuPrimitive.Portal>
        <MenuPrimitive.Content className="ill-sd-layer sd-menu" align={align} sideOffset={6} aria-label={label}>
          {children}
        </MenuPrimitive.Content>
      </MenuPrimitive.Portal>
    </MenuPrimitive.Root>
  );
}

export function MenuItem({
  children,
  onSelect,
  icon,
  shortcut,
  disabled,
}: {
  children: ReactNode;
  onSelect(): void;
  icon?: ReactNode;
  shortcut?: string;
  disabled?: boolean;
}) {
  return (
    <MenuPrimitive.Item className="sd-menu__item" onSelect={onSelect} disabled={disabled}>
      <span className="sd-menu__icon" aria-hidden>
        {icon}
      </span>
      <span className="sd-menu__label">{children}</span>
      {shortcut ? <Kbd>{shortcut}</Kbd> : null}
    </MenuPrimitive.Item>
  );
}

export function MenuCheckboxItem({
  children,
  checked,
  onCheckedChange,
}: {
  children: ReactNode;
  checked: boolean;
  onCheckedChange(checked: boolean): void;
}) {
  return (
    <MenuPrimitive.CheckboxItem
      className="sd-menu__item"
      checked={checked}
      onCheckedChange={onCheckedChange}
      onSelect={(event) => event.preventDefault()}
    >
      <span className="sd-menu__icon" aria-hidden>
        <MenuPrimitive.ItemIndicator>
          <Check size={14} />
        </MenuPrimitive.ItemIndicator>
      </span>
      <span className="sd-menu__label">{children}</span>
    </MenuPrimitive.CheckboxItem>
  );
}

export const MenuSeparator = () => <MenuPrimitive.Separator className="sd-menu__separator" />;
export const MenuLabel = ({ children }: { children: ReactNode }) => (
  <MenuPrimitive.Label className="sd-menu__heading">{children}</MenuPrimitive.Label>
);
