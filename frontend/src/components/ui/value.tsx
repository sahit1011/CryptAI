import * as React from "react"

import { cn } from "@/lib/utils"
import { safeNum } from "@/lib/utils"

/*
 * Numeric primitives — the terminal's typographic backbone.
 *
 * <Value>  : any monospace number (price, size, timestamp-as-text). Neutral color.
 * <PnL>    : sign-aware profit/loss. Emerald when >= 0, red when < 0. Optional +/-
 *            sign, optional % suffix, optional colored background chip.
 *
 * BOTH render via the `.num` utility (Geist Mono + tabular-nums) so columns align.
 * Section agents MUST use these (or the `.num` class) for every number on screen.
 */

type ValueProps = React.ComponentProps<"span"> & {
  /** Fixed decimal places. If omitted, the child is rendered as-is (already formatted). */
  decimals?: number
  /** Prefix glued to the number, e.g. "$". */
  prefix?: string
  /** Suffix glued to the number, e.g. "%" or "x". */
  suffix?: string
  /** Raw numeric value; when provided it is formatted and overrides children. */
  value?: number | string | null | undefined
  /** Placeholder shown when value is non-finite / missing. */
  placeholder?: string
}

function formatNumber(value: number, decimals?: number): string {
  if (decimals === undefined) {
    // Sensible default grouping without forcing decimals.
    return value.toLocaleString("en-US", { maximumFractionDigits: 8 })
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function Value({
  className,
  decimals,
  prefix,
  suffix,
  value,
  placeholder = "—",
  children,
  ...props
}: ValueProps) {
  let body: React.ReactNode = children
  if (value !== undefined) {
    const n = safeNum(value, NaN)
    body = Number.isFinite(n) ? formatNumber(n, decimals) : placeholder
  }
  return (
    <span data-slot="value" className={cn("num", className)} {...props}>
      {prefix}
      {body}
      {suffix}
    </span>
  )
}

type PnLProps = Omit<ValueProps, "value"> & {
  /** Signed numeric value. Sign drives the color. */
  value: number | string | null | undefined
  /** Show an explicit leading "+" on positive values (default true). */
  showSign?: boolean
  /** Append "%". */
  percent?: boolean
  /** Render inside a colored chip (default false — inline colored text). */
  chip?: boolean
  /** Treat exactly-zero as neutral gray rather than profit-green (default true). */
  neutralZero?: boolean
}

function PnL({
  className,
  value,
  decimals = 2,
  prefix,
  suffix,
  showSign = true,
  percent = false,
  chip = false,
  neutralZero = true,
  placeholder = "—",
  ...props
}: PnLProps) {
  const n = safeNum(value, NaN)
  const finite = Number.isFinite(n)
  const positive = finite && n > 0
  const negative = finite && n < 0
  const zero = finite && n === 0

  const tone = !finite
    ? "text-subtle-foreground"
    : negative
      ? "text-loss"
      : zero && neutralZero
        ? "text-muted-foreground"
        : "text-profit"

  const chipTone = !finite
    ? ""
    : negative
      ? "bg-loss-muted"
      : zero && neutralZero
        ? "bg-elevated"
        : "bg-profit-muted"

  // toLocaleString already carries the minus sign; we only prepend a "+".
  const rendered = finite
    ? `${positive && showSign ? "+" : ""}${prefix ?? ""}${n.toLocaleString(
        "en-US",
        { minimumFractionDigits: decimals, maximumFractionDigits: decimals },
      )}${percent ? "%" : ""}${suffix ?? ""}`
    : placeholder

  return (
    <span
      data-slot="pnl"
      className={cn(
        "num tabular-nums",
        tone,
        chip && "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
        chip && chipTone,
        className,
      )}
      {...props}
    >
      {rendered}
    </span>
  )
}

export { Value, PnL }
