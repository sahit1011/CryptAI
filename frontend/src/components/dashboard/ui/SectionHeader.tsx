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
        // Compact working header — an app section is a workspace, not a landing
        // hero. No icon chip; icon/iconColor stay in the props for caller
        // compatibility but are intentionally unrendered (void below).
        <div className={cn("flex items-end justify-between gap-4 mb-6", className)}>
            {void Icon}
            {void iconColor}
            <div>
                <h1 className="heading-2 text-foreground">{title}</h1>
                {description && (
                    <p className="body-sm mt-1 max-w-2xl">{description}</p>
                )}
            </div>

            {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
        </div>
    );
}
