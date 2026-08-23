# Frontend Design Specification: Multi-Agent Crypto Trading Platform

## 1. Design Philosophy & Aesthetic
**Inspiration:** Walbi Trading, Linear, Vercel.
**Theme:** "Cyber-Professional". Dark mode default. Deep blues/blacks (`#0a0a0a`, `#0f172a`) with vibrant neon accents (Electric Blue for Data, Purple for Strategy, Green for Success, Red for Risk).
**Core Principles:**
-   **Glassmorphism:** Subtle translucency in panels to show depth.
-   **Micro-interactions:** Hover states, smooth transitions, live pulsing indicators for "Agent Heartbeats".
-   **Data Density:** High information density but clean typography (Inter/JetBrains Mono).

## 2. Technology Stack
-   **Framework:** Next.js 14+ (App Router)
-   **Language:** TypeScript
-   **Styling:** Tailwind CSS
-   **Components:** Shadcn/UI (Radix Primitives)
-   **Animations:** Framer Motion (for smooth layout shifts and entry animations)
-   **Charts:** Recharts or Lightweight-charts (TradingView style)
-   **State Management:** Zustand (client state), TanStack Query (server state)
-   **Icons:** Lucide React

## 3. User Experience (UX) Flow

### 3.1 Onboarding
1.  **Landing Page:** "Automate your trading with Institutional-Grade AI Agents."
2.  **Auth:** Sign up/Login (Clerk/Supabase).
3.  **Setup Wizard:**
    -   Step 1: Connect Exchange (API Key/Secret input with encryption warning).
    -   Step 2: Define Risk Profile (Conservative/Aggressive).
    -   Step 3: Activate Agents.

### 3.2 The Dashboard (The "Cockpit")
The main view where users spend 90% of their time.
-   **Top Bar:** Global status (System Health), Wallet Balance, User Profile.
-   **Left Sidebar:** Navigation (Dashboard, Analytics, Agents, Settings, Logs).
-   **Main Content:**
    -   **Portfolio Summary:** Total Equity, 24h PnL, Open Positions count.
    -   **Live Agent Feed (The "Brain"):** A scrolling terminal-like feed showing real-time agent thoughts.
        -   *Example:* `[ANALYSIS] Detected Bullish Divergence on BTC/USDT 15m.`
        -   *Example:* `[RISK] Validating trade... Approved (Risk: 1.2%).`
    -   **Active Trades:** Cards showing open positions with live PnL and "Close" button.
    -   **Chart:** Main price chart with agent annotations (Buy/Sell markers).

### 3.3 Agent Visualization (Unique Feature)
A dedicated view to see the "Multi-Agent" system in action.
-   **Visual Graph:** A node-link diagram showing Data -> Analysis -> Strategy -> Risk -> Execution.
-   **Active Nodes:** Nodes light up when active.
-   **Inspection:** Click a node to see its current context/memory.

## 4. Component Architecture

### Atoms
-   `StatusBadge`: (Live, Offline, Error)
-   `CryptoIcon`: Dynamic icon loader
-   `NeonButton`: Primary action button with glow

### Molecules
-   `TradeCard`: Displays Symbol, Side, Entry, Current Price, PnL, ROI.
-   `MetricCard`: Label, Value, Trend indicator.
-   `AgentLogItem`: Timestamp, Agent Name, Message, Severity.

### Organisms
-   `TradingViewChart`: Wrapper around charting library.
-   `AgentOrchestratorView`: Interactive graph of agent states.
-   `ConnectExchangeForm`: Secure form for API keys.

## 5. Integration Strategy
-   **Backend:** Python (FastAPI) exposing REST endpoints + WebSockets.
-   **Real-time:**
    -   `/ws/market-data`: Live prices.
    -   `/ws/agent-events`: Agent logs and state changes.
    -   `/ws/user-updates`: Order fills, PnL updates.

## 6. Deployment
-   **Frontend:** Vercel (Auto-deploy from Git).
-   **Backend:** Dockerized on AWS/Railway/Render.
