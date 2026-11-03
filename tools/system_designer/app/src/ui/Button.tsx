import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { LoaderCircle } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from './cn';
import { Tooltip } from './Tooltip';

export const buttonClass = cva('sd-btn', {
  variants: {
    variant: {
      primary: 'sd-btn--primary',
      secondary: 'sd-btn--secondary',
      quiet: 'sd-btn--quiet',
      danger: 'sd-btn--danger',
    },
    size: { sm: 'sd-btn--sm', md: '' },
  },
  defaultVariants: { variant: 'secondary', size: 'md' },
});

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonClass> {
  /** Shows a spinner and disables the button while an action runs. */
  loading?: boolean;
  /** An icon before the label (decorative; the label names the button). */
  icon?: ReactNode;
  /** Render the child element (a link) with button styling. */
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, loading = false, icon, asChild = false, className, children, disabled, type, ...props },
  ref,
) {
  const classes = cn(buttonClass({ variant, size }), loading && 'sd-btn--loading', className);
  if (asChild)
    return (
      <Slot ref={ref} className={classes} {...props}>
        {children}
      </Slot>
    );
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <LoaderCircle className="sd-spin" aria-hidden size={16} /> : icon ? <span className="sd-btn__icon" aria-hidden>{icon}</span> : null}
      {children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, 'children' | 'icon'> {
  /** The accessible name, rendered as visually hidden text and shown as the tooltip. */
  label: string;
  icon: ReactNode;
}

/** A square icon-only button whose name is real (hidden) text, so tests and screen readers find it. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, className, variant = 'quiet', ...props },
  ref,
) {
  return (
    <Tooltip content={label}>
      <Button ref={ref} variant={variant} className={cn('sd-btn--icon', className)} {...props}>
        <span aria-hidden className="sd-btn__icon">
          {icon}
        </span>
        <span className="sd-sr-only">{label}</span>
      </Button>
    </Tooltip>
  );
});
