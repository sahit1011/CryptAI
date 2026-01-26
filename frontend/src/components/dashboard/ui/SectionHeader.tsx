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
    iconColor = "bg-emerald-500/10 text-emerald-400",
    actions,
    className,
}: SectionHeaderProps) {
    return (
        <div className={cn("flex items-start justify-between gap-4 mb-8", className)}>
            <div className="flex items-start gap-4">
                {Icon && (
                    <div className={cn("p-3 rounded-xl", iconColor)}>
                        <Icon className="w-6 h-6" />
                    </div>
                )}
                <div>
                    <h1 className="display-3 text-white mb-2">{title}</h1>
                    {description && (
                        <p className="body-md text-muted-foreground max-w-2xl">{description}</p>
                    )}
                </div>
            </div>

            {actions && <div className="flex items-center gap-3">{actions}</div>}
        </div>
    );
}
