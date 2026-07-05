"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/*
 * ConnectionStatus — a small live-feed pill. Drive it from the WS connection
 * status in the store (`useMarketStore().status`). Emerald=live, amber=connecting/
 * reconnecting, red=error, gray=closed. Numbers/text stay sans (it's a label).
 */

export type ConnState =
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "error"

const META: Record<
  ConnState,
  { label: string; dot: string; text: string; pulse?: boolean }
> = {
  open: { label: "Live", dot: "bg-profit", text: "text-profit", pulse: true },
  connecting: {
    label: "Connecting",
    dot: "bg-warning",
    text: "text-warning",
    pulse: true,
  },
  reconnecting: {
    label: "Reconnecting",
    dot: "bg-warning",
    text: "text-warning",
    pulse: true,
  },
  error: { label: "Error", dot: "bg-loss", text: "text-loss" },
  closed: { label: "Offline", dot: "bg-subtle-foreground", text: "text-muted-foreground" },
}

function ConnectionStatus({
  status,
  className,
  ...props
}: React.ComponentProps<"span"> & { status: ConnState }) {
  const m = META[status] ?? META.closed
  return (
    <span
      data-slot="connection-status"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border bg-elevated/60 px-2 py-0.5 text-[11px] font-medium",
        m.text,
        className,
      )}
      {...props}
    >
      <span className="relative flex size-1.5">
        {m.pulse ? (
          <span
            className={cn(
              "absolute inline-flex size-full animate-ping rounded-full opacity-60",
              m.dot,
            )}
          />
        ) : null}
        <span className={cn("relative inline-flex size-1.5 rounded-full", m.dot)} />
      </span>
      {m.label}
    </span>
  )
}

export { ConnectionStatus }
