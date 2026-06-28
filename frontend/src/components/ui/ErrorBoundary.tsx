"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
    children: ReactNode;
    fallback?: ReactNode;
}

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
}

/**
 * Top-level React error boundary. Catches render-time exceptions anywhere in
 * the subtree (e.g. a widget choking on malformed live data) and shows a
 * recoverable fallback instead of unmounting the whole dashboard.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        // Surface to the console; a real deployment can forward this to logging.
        console.error("Dashboard error boundary caught:", error, info);
    }

    handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;
            return (
                <div className="flex h-full w-full flex-col items-center justify-center gap-4 p-8 text-center">
                    <div className="text-lg font-semibold text-white">Something went wrong</div>
                    <p className="max-w-md text-sm text-muted-foreground">
                        A part of the dashboard failed to render. Your data is safe — try
                        reloading this view.
                    </p>
                    <button
                        onClick={this.handleReset}
                        className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-400 transition-colors hover:bg-emerald-500/20"
                    >
                        Try again
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}
