# DESIGN.md — CryptAI

Dark-only. Tokens live in `src/app/globals.css` (@theme + :root, OKLCH). This
file describes intent; the CSS is the source of truth.

## Theme
"Terminal-grade restraint": near-black neutral canvas, crimson as the single
brand hue, emerald/red reserved for P&L semantics only. Fine film grain
(`.grain`) on marketing/auth surfaces. Depth via hairlines and layer steps —
no drop shadows or glows as structure.

## Color
- Canvas ladder: `--background` oklch(.135 0 0) → `--surface` .165 → `--elevated` .2
- Text: `--foreground` .97 · `--muted-foreground` .66 · `--subtle-foreground` .5
- Hairlines: `--border` white/8% · `--border-strong` white/14%
- Brand: crimson ramp `--accent-50..700` (hue ~26); `--accent` = 500;
  headline/serif accents use `accent-300`; fills use deep maroon `--primary`
  (never full-bright red buttons)
- Semantics: `--profit` emerald · `--loss` red · `--warning` amber · `--info` blue.
  P&L colors are untouchable by branding.

## Typography
- Sans: Geist (`--font-sans`) — UI + body. Weights cap at 600.
- Mono: Geist Mono (`--font-mono`) via `.num` — EVERY number/price/timestamp,
  tabular-nums + slashed zero.
- Display serif: Instrument Serif italic (`--font-serif`) — hero-scale accent
  words only (crimson `accent-300`), never body text.
- Scale: `.display-1/2/3` with progressive negative tracking (-.02 → -.035em);
  `.eyebrow` mono kicker exists but is used ONCE (hero) by design.

## Radius & borders
Strictly 4 / 6 / 8px (`--radius-sm/md/lg/xl`; 2xl+ capped at 8). `rounded-full`
only for status dots and countable badges. Cards = `border border-border
bg-surface`; grouped rows = `divide-border` or `gap-px bg-border` grids.

## Motion
- UI state: `transition-[colors] duration-150`; section switches 8px/150–300ms.
- Reveals: whileInView once, ease `[0.16,1,0.3,1]`, shaped to the content
  (pipeline sweeps left→right; dots stagger in; headline types).
- Signature loops: hero quad demo (independent per-quad periods), architecture
  pulse (1.4s per stage). All disabled under prefers-reduced-motion.
- Bans: bounce/elastic, hover scale-pops, shine sweeps, gradient text.

## Components
- Buttons: `components/ui/button.tsx` variants; default = maroon fill + subtle
  accent border; destructive/success are tinted, not solid.
- Numbers: `<Value>/<PnL>` primitives or `.num`.
- Empty states: `components/ui/states.tsx` — must say WHY empty and what
  unlocks it (e.g. "AI engine is paused").
- Section headers (app): compact `SectionHeader` — no icon chips.
- Landing sections each own a distinct structure: manifesto, spec-sheet table,
  cycle-dot band, divided pipeline strip, terminal-prompt CTA.

## Layout
Landing container `max-w-6xl`; hero claim column `max-w-2xl` with the ghost
quad demo as a 3D background layer (masked, never a boxed card). Dashboard:
sidebar rail (mobile drawer) + `max-w-7xl` content; KPI band = one bordered
`gap-px` grid.
