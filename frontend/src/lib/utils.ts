import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names with Tailwind-aware conflict resolution.
 * Standard shadcn/ui helper, imported as `cn` across ~23 components.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Coerce any value to a finite number, falling back to `fallback` (default 0)
 * for null/undefined/NaN/Infinity. Use before any arithmetic or `.toFixed()`
 * on values that originate from the network (WebSocket payloads, API JSON),
 * which can be missing, strings, or NaN.
 */
export function safeNum(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : parseFloat(String(value));
  return Number.isFinite(n) ? n : fallback;
}

/**
 * Format a numeric value with fixed decimals, guarding against NaN/undefined.
 * Returns `placeholder` (default "—") when the value isn't a finite number.
 */
export function safeFixed(
  value: unknown,
  digits = 2,
  placeholder = "—",
): string {
  const n = typeof value === "number" ? value : parseFloat(String(value));
  return Number.isFinite(n) ? n.toFixed(digits) : placeholder;
}

/**
 * Safe division that returns `fallback` (default 0) when the denominator is
 * zero or either operand is non-finite. Avoids NaN/Infinity leaking into
 * widths, percentages, and ratios.
 */
export function safeDiv(
  numerator: unknown,
  denominator: unknown,
  fallback = 0,
): number {
  const a = safeNum(numerator, NaN);
  const b = safeNum(denominator, NaN);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return fallback;
  return a / b;
}
