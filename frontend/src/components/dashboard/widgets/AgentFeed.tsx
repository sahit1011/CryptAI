
"use client"

import { useRef, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { useStore } from "@/store/useStore"
import { cn } from "@/lib/utils"
import { GlassCard } from "@/components/ui/glass-card"

export function AgentFeed() {
    const { agentLogs } = useStore()
    const scrollRef = useRef<HTMLDivElement>(null)

    // Smooth auto-scroll to bottom when new logs arrive (like a real terminal)
    useEffect(() => {
        if (scrollRef.current) {
            const scrollContainer = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
            if (scrollContainer) {
                // Smooth scroll animation
                scrollContainer.scrollTo({
                    top: scrollContainer.scrollHeight,
                    behavior: 'smooth'
                });
            }
        }
    }, [agentLogs]);

    return (
        <GlassCard className="flex flex-col h-[500px] overflow-hidden">
            <div className="p-4 border-b border-white/5 bg-white/5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-white">Agent Neural Feed</h3>
                    <span className="text-xs text-muted-foreground font-mono">
                        ({agentLogs.length} events)
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs text-emerald-500 font-medium">Live</span>
                </div>
            </div>
            <ScrollArea className="flex-1 p-4" ref={scrollRef}>
                <div className="space-y-2">
                    {agentLogs.length === 0 && (
                        <div className="text-center text-muted-foreground text-sm py-10">
                            <div className="animate-pulse">Waiting for agent activity...</div>
                            <div className="text-xs mt-2 opacity-50">
                                Trading cycles run every 5 minutes
                            </div>
                        </div>
                    )}
                    {agentLogs.map((log, index) => (
                        <div
                            key={log.id}
                            className="flex items-start gap-3 text-sm font-mono animate-fade-in py-1.5 px-2 rounded hover:bg-white/5 transition-colors"
                            style={{
                                animation: `fadeIn 0.3s ease-in-out ${index * 0.05}s both`
                            }}
                        >
                            <span className="text-muted-foreground text-xs mt-0.5 min-w-[60px]">
                                {log.timestamp}
                            </span>
                            <Badge variant="outline" className={cn(
                                "text-[10px] px-2 py-0.5 border-0 font-medium min-w-[80px] text-center",
                                log.agent === 'DATA' && "text-blue-400 bg-blue-400/10",
                                log.agent === 'ANALYSIS' && "text-purple-400 bg-purple-400/10",
                                log.agent === 'STRATEGY' && "text-yellow-400 bg-yellow-400/10",
                                log.agent === 'RISK' && "text-red-400 bg-red-400/10",
                                log.agent === 'EXECUTION' && "text-emerald-400 bg-emerald-400/10",
                            )}>
                                {log.agent}
                            </Badge>
                            <span className={cn(
                                "flex-1 leading-relaxed",
                                log.severity === 'success' && "text-emerald-300",
                                log.severity === 'warning' && "text-yellow-300",
                                log.severity === 'error' && "text-red-300",
                                log.severity === 'info' && "text-gray-300"
                            )}>
                                {log.message}
                            </span>
                        </div>
                    ))}
                </div>
            </ScrollArea>

            {/* Scroll indicator */}
            {agentLogs.length > 10 && (
                <div className="absolute bottom-20 right-6 pointer-events-none">
                    <div className="bg-white/10 backdrop-blur-sm px-3 py-1 rounded-full text-xs text-white/60 animate-pulse">
                        ↓ Auto-scrolling
                    </div>
                </div>
            )}
        </GlassCard>
    )
}

