/*
 * BackgroundGrid — the shared landing atmosphere.
 *
 * Two quiet layers (back to front):
 *   1. .aurora           — two faint drifting crimson radial washes over canvas
 *   2. .grid-perspective — hairline crimson grid, masked to fade at the edges
 *
 * Deliberately restrained: no particles, no motes, no floating decoration —
 * decorative particle fields are one of the clearest "generated" tells. The
 * atmosphere's job is depth, not spectacle; content carries the page.
 */
export const BackgroundGrid = () => {
    return (
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
            <div className="aurora">
                <div className="grid-perspective" />
            </div>
        </div>
    );
};
