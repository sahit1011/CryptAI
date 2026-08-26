/**
 * The dashboard shell moved to the (app) route group when ?section= became real routes.
 * This is a pass-through so /dashboard can redirect without mounting a second shell —
 * and without running the auth/onboarding checks twice on the way to /desk.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
