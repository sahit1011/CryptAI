import { NextResponse } from 'next/server'
import { createClient } from '@/utils/supabase/server'

export async function GET(request: Request) {
    const { searchParams, origin } = new URL(request.url)
    const code = searchParams.get('code')
    const next = searchParams.get('next') ?? '/dashboard'

    // The provider reports its own failures here, not as a missing code — without
    // reading these, a rejected consent and an expired code are indistinguishable
    // from "no code at all", which is why this route used to fail mutely.
    const providerError = searchParams.get('error')
    const providerErrorDescription = searchParams.get('error_description')

    if (providerError) {
        console.error(
            `[auth/callback] provider returned an error: ${providerError}` +
            (providerErrorDescription ? ` — ${providerErrorDescription}` : '')
        )
        return NextResponse.redirect(`${origin}/auth/auth-code-error`)
    }

    if (!code) {
        console.error(
            '[auth/callback] no ?code and no ?error. The provider redirected here without ' +
            'completing the exchange — usually this origin is missing from the Supabase ' +
            `Redirect URLs allowlist (this request came from ${origin}).`
        )
        return NextResponse.redirect(`${origin}/auth/auth-code-error`)
    }

    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
        return NextResponse.redirect(`${origin}${next}`)
    }

    // Logged, never rendered: the message can carry provider and token detail that
    // does not belong in a page the user (or a shoulder-surfer) can read.
    console.error(`[auth/callback] code exchange failed: ${error.message}`)
    return NextResponse.redirect(`${origin}/auth/auth-code-error`)
}
