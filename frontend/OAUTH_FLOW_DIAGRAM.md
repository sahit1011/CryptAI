# 🔄 Google OAuth Authentication Flow

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER AUTHENTICATION FLOW                      │
└─────────────────────────────────────────────────────────────────┘

1. User visits Login/Signup Page
   │
   ├─ Email/Password Flow
   │  └─> Supabase Auth → Dashboard
   │
   └─ Google OAuth Flow (What we're setting up)
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: User clicks "Google" button                              │
│ Location: /auth/login or /auth/signup                            │
│ Code: handleGoogleLogin() / handleGoogleSignup()                 │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 2: Supabase initiates OAuth flow                            │
│ Method: supabase.auth.signInWithOAuth({ provider: "google" })    │
│ Redirects to: Google OAuth consent screen                        │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 3: User authenticates with Google                           │
│ - User selects Google account                                    │
│ - User grants permissions                                        │
│ - Google generates authorization code                            │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 4: Google redirects to Supabase                             │
│ Redirect URL: https://tmloozpmxffxfitxnofo.supabase.co/         │
│               auth/v1/callback                                   │
│ Parameters: ?code=AUTHORIZATION_CODE                             │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 5: Supabase exchanges code for session                      │
│ - Supabase validates the authorization code                      │
│ - Creates user session                                           │
│ - Generates access token and refresh token                       │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 6: Supabase redirects to your app                           │
│ Redirect URL: http://localhost:3000/auth/callback                │
│ Parameters: ?code=SESSION_CODE                                   │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 7: Your callback handler processes the code                 │
│ File: /src/app/auth/callback/route.ts                            │
│ Method: supabase.auth.exchangeCodeForSession(code)               │
└──────────────────────────────────────────────────────────────────┘
      │
      ├─ Success ──────────────────────────────────────┐
      │                                                 │
      ▼                                                 ▼
┌──────────────────────────────┐         ┌──────────────────────────┐
│ Redirect to Dashboard        │         │ Redirect to Error Page   │
│ URL: /dashboard              │         │ URL: /auth/auth-code-error│
│ User is now authenticated! ✅│         │ Show error message ❌     │
└──────────────────────────────┘         └──────────────────────────┘
```

---

## 🔐 Security Components

### Session Management
```
┌─────────────────────────────────────────────────────────────────┐
│                      MIDDLEWARE LAYER                            │
│  File: /src/middleware.ts                                        │
│                                                                   │
│  On every request:                                               │
│  1. Check for existing session                                   │
│  2. Refresh token if needed                                      │
│  3. Update session cookies                                       │
│  4. Allow/deny access to protected routes                        │
└─────────────────────────────────────────────────────────────────┘
```

### Client-Side Auth
```
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE CLIENT                               │
│  File: /src/utils/supabase/client.ts                             │
│                                                                   │
│  - Used in browser components                                    │
│  - Manages auth state                                            │
│  - Handles OAuth redirects                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Server-Side Auth
```
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE SERVER                               │
│  File: /src/utils/supabase/server.ts                             │
│                                                                   │
│  - Used in server components and API routes                      │
│  - Reads session from cookies                                    │
│  - Validates user authentication                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Configuration Points

### 1. Google Cloud Console
```
┌─────────────────────────────────────────────────────────────────┐
│ OAuth 2.0 Client Configuration                                   │
├─────────────────────────────────────────────────────────────────┤
│ Authorized JavaScript Origins:                                   │
│  • http://localhost:3000                                         │
│  • https://your-production-domain.com                            │
│                                                                   │
│ Authorized Redirect URIs:                                        │
│  • https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback   │
│  • http://localhost:3000/auth/callback                           │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Supabase Dashboard
```
┌─────────────────────────────────────────────────────────────────┐
│ Authentication → Providers → Google                              │
├─────────────────────────────────────────────────────────────────┤
│ Enabled: ✅ ON                                                   │
│ Client ID: [YOUR_GOOGLE_CLIENT_ID]                              │
│ Client Secret: [YOUR_GOOGLE_CLIENT_SECRET]                      │
│                                                                   │
│ Redirect URL (auto-configured):                                 │
│  https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback     │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Environment Variables
```
┌─────────────────────────────────────────────────────────────────┐
│ File: .env.local                                                 │
├─────────────────────────────────────────────────────────────────┤
│ NEXT_PUBLIC_SUPABASE_URL=                                        │
│   https://tmloozpmxffxfitxnofo.supabase.co                      │
│                                                                   │
│ NEXT_PUBLIC_SUPABASE_ANON_KEY=                                   │
│   eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Data Flow

```
User Action → Frontend → Supabase → Google → Supabase → Frontend
    │            │          │          │         │          │
    │            │          │          │         │          │
    ▼            ▼          ▼          ▼         ▼          ▼
  Click      OAuth      Request    Auth      Create     Redirect
  Button     Init       Auth       User      Session    Dashboard
```

---

## ✅ Checklist for Testing

- [ ] Google OAuth credentials created
- [ ] Credentials added to Supabase
- [ ] Redirect URLs configured in Google Console
- [ ] Site URL configured in Supabase
- [ ] Development server running (`npm run dev`)
- [ ] Can access login page
- [ ] Google button appears
- [ ] Clicking Google button redirects to Google
- [ ] After Google auth, redirects back to app
- [ ] User lands on dashboard
- [ ] Session persists on page refresh

---

## 🚨 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Redirect URI mismatch" | Verify exact match in Google Console |
| "OAuth not configured" | Complete OAuth consent screen setup |
| "Session not found" | Check middleware is running |
| "Infinite redirect loop" | Clear cookies and check callback route |
| "User not created" | Check Supabase logs in dashboard |

---

## 🎉 Success Indicators

When everything is working correctly:

1. ✅ Google button is visible on login/signup pages
2. ✅ Clicking Google opens Google's login page
3. ✅ After Google login, user is redirected to dashboard
4. ✅ User session persists across page refreshes
5. ✅ User can log out and log back in
6. ✅ No errors in browser console
7. ✅ No errors in terminal/server logs
