"use client"

import { EmptyState } from "@/components/ui/states"

/*
 * OpenOrdersTab — honest by design. Brackets are placed atomically today
 * (entry + SL + TPs in one risk-gated call) and tracked as positions; a
 * working-orders API (list / amend / cancel) hasn't shipped. No fake table.
 * The tab slot is reserved so the layout doesn't shift when it lands.
 */
export function OpenOrdersTab() {
    return (
        <EmptyState
            title="Working orders land with the order-management API"
            description="Today every bracket is placed atomically — entry, stop and take-profits together — and shows up under Positions the moment it books. Resting limit orders, amend and cancel arrive with the orders API."
        />
    )
}
