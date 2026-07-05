import * as React from "react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

/*
 * Honest state primitives. The brief forbids fabricated data — when there is no
 * real backend data, render one of these instead of placeholder numbers.
 *
 * <EmptyState> : nothing to show yet (no positions, no logs…).
 * <ErrorState> : a fetch/WS error, with an optional retry.
 * <LoadingState>: neutral centered spinner+label for in-flight loads.
 */

type StateShellProps = React.ComponentProps<"div"> & {
  icon?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
}

function StateShell({
  className,
  icon,
  title,
  description,
  children,
  ...props
}: StateShellProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
      {...props}
    >
      {icon ? (
        <div className="mb-1 flex size-9 items-center justify-center rounded-full border border-border bg-elevated text-muted-foreground [&_svg]:size-4">
          {icon}
        </div>
      ) : null}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-xs text-xs text-muted-foreground">{description}</p>
      ) : null}
      {children}
    </div>
  )
}

function EmptyState({
  icon,
  title = "Nothing here yet",
  description,
  className,
  children,
  ...props
}: Partial<StateShellProps>) {
  return (
    <StateShell
      data-slot="empty-state"
      icon={icon}
      title={title}
      description={description}
      className={className}
      {...props}
    >
      {children}
    </StateShell>
  )
}

type ErrorStateProps = Partial<StateShellProps> & {
  /** Raw error message shown in monospace below the description. */
  error?: string | null
  onRetry?: () => void
  retryLabel?: string
}

function ErrorState({
  icon,
  title = "Something went wrong",
  description,
  error,
  onRetry,
  retryLabel = "Retry",
  className,
  ...props
}: ErrorStateProps) {
  return (
    <StateShell
      data-slot="error-state"
      icon={icon}
      title={title}
      description={description}
      className={className}
      {...props}
    >
      {error ? (
        <p className="num max-w-full truncate text-xs text-loss">{error}</p>
      ) : null}
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-1" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </StateShell>
  )
}

function LoadingState({
  title = "Loading…",
  className,
  ...props
}: Partial<StateShellProps>) {
  return (
    <div
      data-slot="loading-state"
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
      {...props}
    >
      <span className="size-4 animate-spin rounded-full border-2 border-border border-t-accent" />
      <p className="text-xs text-muted-foreground">{title}</p>
    </div>
  )
}

export { EmptyState, ErrorState, LoadingState }
