import * as React from "react"

import { cn } from "@/lib/utils"
import { PnL, Value } from "@/components/ui/value"

/*
 * StatTile — a single labelled metric block for KPI rows (equity, P&L, win rate…).
 *
 * Label is sans (uppercase, muted); the value is monospace via <Value>/<PnL>.
 * Use `pnl` to make the value sign-aware (emerald/red). Pass `loading` for a
 * skeleton row, or render a custom node via `children` to fully control the value.
 */

type StatTileProps = React.ComponentProps<"div"> & {
  label: React.ReactNode
  /** Formatted string OR raw number (paired with `decimals`/`prefix`/`suffix`). */
  value?: React.ReactNode
  /** When true, format `value` as sign-aware P&L (emerald/red, +/-). */
  pnl?: boolean
  decimals?: number
  prefix?: string
  suffix?: string
  percent?: boolean
  /** Treat `value` as USD and render as ₹ at the live rate. */
  money?: boolean
  /** Secondary line under the value (e.g. a delta or context). */
  hint?: React.ReactNode
  /** Optional leading icon. */
  icon?: React.ReactNode
  loading?: boolean
}

function StatTile({
  className,
  label,
  value,
  pnl = false,
  decimals,
  prefix,
  suffix,
  percent = false,
  money = false,
  hint,
  icon,
  loading = false,
  children,
  ...props
}: StatTileProps) {
  const isRawNumber = typeof value === "number" || typeof value === "string"

  return (
    <div
      data-slot="stat-tile"
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5",
        className,
      )}
      {...props}
    >
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      {loading ? (
        <div className="h-6 w-24 animate-pulse rounded bg-elevated/70" />
      ) : children ? (
        children
      ) : pnl ? (
        <PnL
          value={value as number}
          decimals={decimals ?? 2}
          prefix={prefix}
          suffix={suffix}
          percent={percent}
          money={money}
          className="text-lg font-semibold"
        />
      ) : isRawNumber ? (
        <Value
          value={value as number | string}
          decimals={decimals}
          prefix={prefix}
          suffix={suffix}
          money={money}
          className="text-lg font-semibold text-foreground"
        />
      ) : (
        <div className="text-lg font-semibold text-foreground">{value}</div>
      )}
      {hint && !loading ? (
        <div className="text-xs text-subtle-foreground">{hint}</div>
      ) : null}
    </div>
  )
}

export { StatTile }
