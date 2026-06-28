import { createBrowserClient } from '@supabase/ssr'

// NEXT_PUBLIC_* values are inlined at build time. They are absent during a CI build
// without secrets (and a real deploy build supplies them), so fall back to harmless
// placeholders to keep prerender/build from crashing. Auth only works once the real
// values are present at build time.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co'
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-anon-key'

export function createClient() {
    return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY)
}
