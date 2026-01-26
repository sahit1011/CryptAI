# 🔑 Supabase Google OAuth - Quick Reference

## Required Information Checklist

### ✅ Already Configured
- [x] Supabase Project URL: `https://tmloozpmxffxfitxnofo.supabase.co`
- [x] Supabase Anon Key: Configured in `.env.local`
- [x] Frontend code setup complete

### ⏳ Need to Configure

#### 1. Google Cloud Console
- [ ] Google OAuth Client ID
- [ ] Google OAuth Client Secret

#### 2. Redirect URLs to Add

**In Google Cloud Console:**
```
https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback
http://localhost:3000/auth/callback
```

**In Supabase Dashboard:**
- Site URL: `http://localhost:3000` (development)
- Redirect URLs: `http://localhost:3000/auth/callback`

---

## 🚀 Quick Setup Steps

1. **Get Google Credentials** (5 minutes)
   - Go to: https://console.cloud.google.com/
   - Create OAuth 2.0 Client ID
   - Copy Client ID and Client Secret

2. **Configure Supabase** (2 minutes)
   - Go to: https://supabase.com/dashboard/project/tmloozpmxffxfitxnofo/auth/providers
   - Enable Google provider
   - Paste Client ID and Client Secret
   - Save

3. **Test** (1 minute)
   - Run: `npm run dev`
   - Visit: http://localhost:3000/auth/login
   - Click "Google" button
   - Should redirect to Google login

---

## 📝 Important URLs

| Purpose | URL |
|---------|-----|
| Google Cloud Console | https://console.cloud.google.com/ |
| Supabase Dashboard | https://supabase.com/dashboard/project/tmloozpmxffxfitxnofo |
| Supabase Auth Providers | https://supabase.com/dashboard/project/tmloozpmxffxfitxnofo/auth/providers |
| Local Login Page | http://localhost:3000/auth/login |
| Local Signup Page | http://localhost:3000/auth/signup |

---

## 🔐 Where to Store Credentials

**Google Client ID & Secret:**
- Store in Supabase Dashboard (Authentication → Providers → Google)
- Do NOT add to `.env.local` (Supabase handles this)

**Supabase Credentials:**
- Already in `.env.local` ✅
- Never commit this file to Git ✅

---

## ✨ What's Already Done

Your application has:
- ✅ Login page with Google OAuth button
- ✅ Signup page with Google OAuth button  
- ✅ Callback handler for OAuth redirects
- ✅ Error page for failed authentication
- ✅ Session management middleware
- ✅ Proper redirect to dashboard after login

---

## 🎯 Next: Just Get Your Google Credentials!

1. Visit Google Cloud Console
2. Create OAuth Client ID
3. Add to Supabase Dashboard
4. Test!

**That's it!** 🎉
