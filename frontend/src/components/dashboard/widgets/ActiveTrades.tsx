
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { GlassCard } from "@/components/ui/glass-card"
import { useStore } from "@/store/useStore"

export function ActiveTrades() {
    const { activeTrades } = useStore()

    return (
        <GlassCard className="overflow-hidden">
            <div className="p-4 border-b border-white/5 flex items-center justify-between">
                <h3 className="font-semibold text-white">Active Positions</h3>
            </div>
            <Table>
                <TableHeader className="bg-white/5">
                    <TableRow className="border-white/5 hover:bg-transparent">
                        <TableHead className="text-muted-foreground">Symbol</TableHead>
                        <TableHead className="text-muted-foreground">Side</TableHead>
                        <TableHead className="text-muted-foreground">Entry</TableHead>
                        <TableHead className="text-muted-foreground">Current</TableHead>
                        <TableHead className="text-muted-foreground">PnL</TableHead>
                        <TableHead className="text-muted-foreground text-right">Action</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {activeTrades.length === 0 && (
                        <TableRow className="border-white/5 hover:bg-transparent">
                            <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                                No active positions
                            </TableCell>
                        </TableRow>
                    )}
                    {activeTrades.map((trade, index) => (
                        <TableRow key={`${trade.id}-${index}`} className="border-white/5 hover:bg-white/5 transition-colors">
                            <TableCell className="font-medium text-white">{trade.symbol}</TableCell>
                            <TableCell>
                                <Badge variant="outline" className={trade.side === 'LONG' ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"}>
                                    {trade.side}
                                </Badge>
                            </TableCell>
                            <TableCell className="text-muted-foreground font-mono">${trade.entry.toLocaleString()}</TableCell>
                            <TableCell className="text-muted-foreground font-mono">${trade.current.toLocaleString()}</TableCell>
                            <TableCell className={trade.pnl >= 0 ? "text-green-400 font-mono" : "text-red-400 font-mono"}>
                                ${trade.pnl.toFixed(2)} ({trade.pnlPercent.toFixed(2)}%)
                            </TableCell>
                            <TableCell className="text-right">
                                <Button variant="destructive" size="sm" className="h-7 text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20">Close</Button>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </GlassCard>
    )
}
