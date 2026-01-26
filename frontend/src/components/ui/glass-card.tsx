import * as React from "react"
import { cn } from "@/lib/utils"

const GlassCard = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & { gradient?: boolean }
>(({ className, gradient, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            "rounded-xl border border-white/10 bg-white/5 backdrop-blur-lg shadow-xl transition-all duration-300 hover:bg-white/10",
            gradient && "bg-gradient-to-br from-white/10 to-white/5",
            className
        )}
        {...props}
    />
))
GlassCard.displayName = "GlassCard"

export { GlassCard }
