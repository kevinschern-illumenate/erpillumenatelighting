import { clsx, type ClassValue } from 'clsx';

/** Join class names; the designer uses plain sd-* classes, so no Tailwind merge is needed. */
export const cn = (...values: ClassValue[]) => clsx(values);
