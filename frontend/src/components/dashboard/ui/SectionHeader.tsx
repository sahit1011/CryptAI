"use client";

import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface SectionHeaderProps {
    title: string;
    description?: string;
    icon?: LucideIcon;
    iconColor?: string;
    actions?: ReactNode;
    className?: string;
}

export function SectionHeader({
    title,
    description,
    icon: Icon,
    iconColor = "bg-accent-muted text-accent-300",
    actions,
    className,
}: SectionHeaderProps) {
    return (
        <div className={cn("flex items-start justify-between gap-4 mb-8", className)}>
            <div className="flex items-start gap-4">
                {Icon && (
                    <div
                        className={cn(
                            "flex size-11 shrink-0 items-center justify-center rounded-xl border border-border",
                            iconColor,
                        )}
                    >
                        <Icon className="size-5" />
                    </div>
                )}
                <div>
                    <h1 className="display-3 text-foreground mb-2">{title}</h1>
                    {description && (
                        <p className="body-md text-muted-foreground max-w-2xl">{description}</p>
                    )}
                </div>
            </div>

            {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
        </div>
    );
}
