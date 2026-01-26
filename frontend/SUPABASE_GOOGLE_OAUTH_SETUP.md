# Supabase Google OAuth Setup Guide

## 🎯 Overview
This guide will help you set up Google OAuth authentication for your CryptAI trading platform using Supabase.

---

## ✅ Current Status

Your application already has:
- ✅ Supabase client configuration
- ✅ Login page with Google OAuth button
- ✅ Signup page with Google OAuth button
- ✅ Auth callback handler
- ✅ Middleware for session management
- ✅ Environment variables configured

---

## 🔑 Required Credentials

You need to obtain and configure the following:

### 1. **Google OAuth Credentials**
- Google Client ID
- Google Client Secret

### 2. **Supabase Configuration**
- Supabase Project URL: `https://tmloozpmxffxfitxnofo.supabase.co` ✅
- Supabase Anon Key: Already configured ✅

---

## 📝 Step-by-Step Setup

### **Step 1: Create Google OAuth Credentials**

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/

2. **Create or Select a Project**
   - Click "Select a Project" → "New Project"
   - Name it (e.g., "CryptAI Trading Platform")
   - Click "Create"

3. **Enable Google+ API**
   - Go to "APIs & Services" → "Library"
   - Search for "Google+ API"
   - Click "Enable"

4. **Configure OAuth Consent Screen**
   - Go to "APIs & Services" → "OAuth consent screen"
   - Select "External" user type
   - Fill in required fields:
     - App name: `CryptAI`
     - User support email: Your email
     - Developer contact email: Your email
   - Click "Save and Continue"
   - Skip scopes (default is fine)
   - Add test users if needed
   - Click "Save and Continue"

5. **Create OAuth 2.0 Client ID**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth 2.0 Client ID"
   - Application type: "Web application"
   - Name: `CryptAI Web Client`
   - **Authorized JavaScript origins:**
     ```
     http://localhost:3000
     https://your-production-domain.com
     ```
   - **Authorized redirect URIs:**
     ```
     https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback
     http://localhost:3000/auth/callback
     ```
   - Click "Create"
   - **SAVE YOUR CLIENT ID AND CLIENT SECRET** (you'll need these next)

---

### **Step 2: Configure Supabase**

1. **Go to Supabase Dashboard**
   - Visit: https://supabase.com/dashboard/project/tmloozpmxffxfitxnofo

2. **Navigate to Authentication Settings**
   - Click "Authentication" in the left sidebar
   - Click "Providers"

3. **Enable Google Provider**
   - Find "Google" in the list
   - Toggle it ON
   - Enter your **Google Client ID**
   - Enter your **Google Client Secret**
   - Click "Save"

4. **Configure Site URL (Optional but Recommended)**
   - Go to "Authentication" → "URL Configuration"
   - Set **Site URL** to:
     - Development: `http://localhost:3000`
     - Production: `https://your-production-domain.com`
   - Set **Redirect URLs** to:
     ```
     http://localhost:3000/auth/callback
     https://your-production-domain.com/auth/callback
     ```

5. **Email Settings (Optional)**
   - Go to "Authentication" → "Email Templates"
   - Customize confirmation and password reset emails if desired

---

### **Step 3: Test the Authentication Flow**

1. **Start your development server:**
   ```bash
   npm run dev
   ```

2. **Navigate to the signup page:**
   ```
   http://localhost:3000/auth/signup
   ```

3. **Click "Google" button**
   - You should be redirected to Google's OAuth consent screen
   - Select your Google account
   - Grant permissions
   - You should be redirected back to `/dashboard`

4. **Test login:**
   - Navigate to `http://localhost:3000/auth/login`
   - Click "Google" button
   - Should automatically log you in

---

## 🔒 Security Best Practices

1. **Environment Variables**
   - Never commit `.env.local` to version control
   - Add it to `.gitignore` (already done)

2. **Supabase Row Level Security (RLS)**
   - Enable RLS on all tables
   - Create policies for authenticated users

3. **Production Deployment**
   - Update redirect URLs in Google Console
   - Update Site URL in Supabase
   - Use environment variables in your hosting platform

---

## 🐛 Troubleshooting

### **Issue: "Invalid redirect URI"**
- **Solution:** Make sure the redirect URI in Google Console exactly matches:
  ```
  https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback
  ```

### **Issue: "OAuth consent screen not configured"**
- **Solution:** Complete the OAuth consent screen setup in Google Console

### **Issue: "User not redirected after login"**
- **Solution:** Check browser console for errors
- Verify callback route is working: `/auth/callback`

### **Issue: "Session not persisting"**
- **Solution:** Check that middleware is properly configured (already done)
- Clear browser cookies and try again

---

## 📚 Additional Resources

- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Supabase Google OAuth Guide](https://supabase.com/docs/guides/auth/social-login/auth-google)

---

## ✨ Next Steps After Setup

1. **Create Protected Routes**
   - Add authentication checks to dashboard pages
   - Redirect unauthenticated users to login

2. **User Profile Management**
   - Create a profile page
   - Allow users to update their information

3. **Database Setup**
   - Create tables for user data
   - Set up Row Level Security policies

4. **Email Verification (Optional)**
   - Enable email confirmation in Supabase
   - Customize email templates

---

## 🎉 You're All Set!

Once you've completed these steps, your Google OAuth authentication should be fully functional!

**Need help?** Let me know if you encounter any issues during setup.
