import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useRef, type ReactNode, type RefObject } from 'react';
import { Button } from './Button';
import { cn } from './cn';

export interface DialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  /** A centred modal, or a drawer from the right edge. */
  variant?: 'center' | 'drawer';
  /** When false, Escape and outside clicks do not close it (terms, session expiry). */
  dismissable?: boolean;
  /** Where focus lands on open; Radix picks the first focusable control otherwise. */
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
  'data-testid'?: string;
}

/** Radix Dialog with the designer's look: focus trap, Escape, focus return and labelled title. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
  variant = 'center',
  dismissable = true,
  initialFocus,
  className,
  ...props
}: DialogProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={cn('ill-sd-layer sd-overlay', variant === 'drawer' && 'sd-overlay--drawer')}>
          <DialogPrimitive.Content
            className={cn('sd-dialog', `sd-dialog--${size}`, variant === 'drawer' && 'sd-dialog--drawer', className)}
            {...(description ? {} : { 'aria-describedby': undefined })}
            onOpenAutoFocus={(event) => {
              if (!initialFocus?.current) return;
              event.preventDefault();
              initialFocus.current.focus();
            }}
            onEscapeKeyDown={(event) => {
              if (!dismissable) event.preventDefault();
            }}
            onInteractOutside={(event) => {
              if (!dismissable) event.preventDefault();
            }}
            data-testid={props['data-testid']}
          >
            <div className="sd-dialog__head">
              <DialogPrimitive.Title className="sd-dialog__title">{title}</DialogPrimitive.Title>
              {dismissable ? (
                <DialogPrimitive.Close className="sd-dialog__close">
                  <X aria-hidden size={18} />
                  <span className="sd-sr-only">Close</span>
                </DialogPrimitive.Close>
              ) : null}
            </div>
            {description ? (
              <DialogPrimitive.Description className="sd-dialog__description">{description}</DialogPrimitive.Description>
            ) : null}
            <div className="sd-dialog__body">{children}</div>
            {footer ? <div className="sd-dialog__footer">{footer}</div> : null}
          </DialogPrimitive.Content>
        </DialogPrimitive.Overlay>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: 'primary' | 'danger';
  onConfirm(): void;
  onCancel(): void;
  'data-testid'?: string;
}

/** Ask before a consequential action. Focus starts on Cancel so Enter never confirms by accident. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = 'Cancel',
  tone = 'primary',
  onConfirm,
  onCancel,
  ...props
}: ConfirmDialogProps) {
  const cancel = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onCancel();
      }}
      title={title}
      size="sm"
      initialFocus={cancel}
      data-testid={props['data-testid']}
      footer={
        <>
          <Button ref={cancel} variant="quiet" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={tone} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
