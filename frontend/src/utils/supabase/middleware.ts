import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

// Placeholder fallbacks keep middleware from throwing when env is absent at build;
// real deploys supply the real values.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co'
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-anon-key'

// Routes that require an authenticated session. Server-side enforcement here is the
// real gate — the client-side check in dashboard/layout is only UX (it hydrates after
// JS and is bypassable on its own).
// Every signed-in route. The (app) route group is a build-time grouping only — it does
// not appear in URLs — so each real path is listed. Missing one here means that page is
// reachable signed-out: the client-side check in the layout hydrates after JS and is
// bypassable on its own, so this list is the actual gate.
// /dashboard and /terminal are retained as redirect stubs to /desk and /chart.
const PROTECTED_PREFIXES = [
    '/dashboard',
    '/terminal',
    '/desk',
    '/chart',
    '/portfolio',
    '/settings',
    '/admin',
]

export async function updateSession(request: NextRequest) {
    let response = NextResponse.next({
        request: {
            headers: request.headers,
        },
    })

    const supabase = createServerClient(
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value }) =>
                        request.cookies.set(name, value)
                    )
                    response = NextResponse.next({
                        request,
                    })
                    cookiesToSet.forEach(({ name, value, options }) =>
                        response.cookies.set(name, value, options)
                    )
                },
            },
        }
    )

    // Refresh the auth token and read the current user.
    const { data: { user } } = await supabase.auth.getUser()

    // Server-side route protection: redirect unauthenticated users away from
    // protected routes before any page renders.
    const { pathname } = request.nextUrl
    const isProtected = PROTECTED_PREFIXES.some(
        (p) => pathname === p || pathname.startsWith(p + '/')
    )
    if (isProtected && !user) {
        const loginUrl = request.nextUrl.clone()
        loginUrl.pathname = '/auth/login'
        loginUrl.searchParams.set('redirect', pathname)
        return NextResponse.redirect(loginUrl)
    }

    return response
}
