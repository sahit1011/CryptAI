import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none transition-colors overflow-hidden",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-accent-muted text-accent-300",
        secondary:
          "border-border bg-elevated text-muted-foreground",
        outline:
          "border-border text-muted-foreground",
        profit:
          "border-transparent bg-profit-muted text-profit",
        loss:
          "border-transparent bg-loss-muted text-loss",
        warning:
          "border-transparent bg-warning-muted text-warning",
        info:
          "border-transparent bg-info-muted text-info",
        /** alias kept for backward compatibility */
        destructive:
          "border-transparent bg-loss-muted text-loss",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span"

  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
