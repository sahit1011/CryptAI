#!/usr/bin/env node

/**
 * Supabase Google OAuth Setup Verification Script
 * 
 * This script checks if all necessary configurations are in place
 * for Google OAuth authentication with Supabase.
 */

const fs = require('fs');
const path = require('path');

console.log('\n🔍 Supabase Google OAuth Setup Verification\n');
console.log('='.repeat(60));

let allChecksPass = true;

// Check 1: Environment Variables
console.log('\n📋 Checking Environment Variables...');
const envPath = path.join(__dirname, '.env.local');

if (fs.existsSync(envPath)) {
    console.log('  ✅ .env.local file exists');

    const envContent = fs.readFileSync(envPath, 'utf-8');

    if (envContent.includes('NEXT_PUBLIC_SUPABASE_URL')) {
        console.log('  ✅ NEXT_PUBLIC_SUPABASE_URL is defined');
    } else {
        console.log('  ❌ NEXT_PUBLIC_SUPABASE_URL is missing');
        allChecksPass = false;
    }

    if (envContent.includes('NEXT_PUBLIC_SUPABASE_ANON_KEY')) {
        console.log('  ✅ NEXT_PUBLIC_SUPABASE_ANON_KEY is defined');
    } else {
        console.log('  ❌ NEXT_PUBLIC_SUPABASE_ANON_KEY is missing');
        allChecksPass = false;
    }
} else {
    console.log('  ❌ .env.local file not found');
    allChecksPass = false;
}

// Check 2: Supabase Client Files
console.log('\n📁 Checking Supabase Client Files...');

const clientPath = path.join(__dirname, 'src', 'utils', 'supabase', 'client.ts');
const serverPath = path.join(__dirname, 'src', 'utils', 'supabase', 'server.ts');
const middlewarePath = path.join(__dirname, 'src', 'utils', 'supabase', 'middleware.ts');

if (fs.existsSync(clientPath)) {
    console.log('  ✅ Client utility exists (src/utils/supabase/client.ts)');
} else {
    console.log('  ❌ Client utility missing');
    allChecksPass = false;
}

if (fs.existsSync(serverPath)) {
    console.log('  ✅ Server utility exists (src/utils/supabase/server.ts)');
} else {
    console.log('  ❌ Server utility missing');
    allChecksPass = false;
}

if (fs.existsSync(middlewarePath)) {
    console.log('  ✅ Middleware utility exists (src/utils/supabase/middleware.ts)');
} else {
    console.log('  ❌ Middleware utility missing');
    allChecksPass = false;
}

// Check 3: Auth Pages
console.log('\n🔐 Checking Authentication Pages...');

const loginPath = path.join(__dirname, 'src', 'app', 'auth', 'login', 'page.tsx');
const signupPath = path.join(__dirname, 'src', 'app', 'auth', 'signup', 'page.tsx');
const callbackPath = path.join(__dirname, 'src', 'app', 'auth', 'callback', 'route.ts');
const errorPath = path.join(__dirname, 'src', 'app', 'auth', 'auth-code-error', 'page.tsx');

if (fs.existsSync(loginPath)) {
    console.log('  ✅ Login page exists');
    const loginContent = fs.readFileSync(loginPath, 'utf-8');
    if (loginContent.includes('signInWithOAuth') && loginContent.includes('google')) {
        console.log('  ✅ Login page has Google OAuth button');
    } else {
        console.log('  ⚠️  Login page might be missing Google OAuth');
    }
} else {
    console.log('  ❌ Login page missing');
    allChecksPass = false;
}

if (fs.existsSync(signupPath)) {
    console.log('  ✅ Signup page exists');
    const signupContent = fs.readFileSync(signupPath, 'utf-8');
    if (signupContent.includes('signInWithOAuth') && signupContent.includes('google')) {
        console.log('  ✅ Signup page has Google OAuth button');
    } else {
        console.log('  ⚠️  Signup page might be missing Google OAuth');
    }
} else {
    console.log('  ❌ Signup page missing');
    allChecksPass = false;
}

if (fs.existsSync(callbackPath)) {
    console.log('  ✅ Callback route exists');
} else {
    console.log('  ❌ Callback route missing');
    allChecksPass = false;
}

if (fs.existsSync(errorPath)) {
    console.log('  ✅ Error page exists');
} else {
    console.log('  ⚠️  Error page missing (optional but recommended)');
}

// Check 4: Middleware
console.log('\n🛡️  Checking Middleware...');

const rootMiddlewarePath = path.join(__dirname, 'src', 'middleware.ts');

if (fs.existsSync(rootMiddlewarePath)) {
    console.log('  ✅ Root middleware exists');
    const middlewareContent = fs.readFileSync(rootMiddlewarePath, 'utf-8');
    if (middlewareContent.includes('updateSession')) {
        console.log('  ✅ Middleware calls updateSession');
    } else {
        console.log('  ⚠️  Middleware might not be configured correctly');
    }
} else {
    console.log('  ❌ Root middleware missing');
    allChecksPass = false;
}

// Check 5: Dependencies
console.log('\n📦 Checking Dependencies...');

const packageJsonPath = path.join(__dirname, 'package.json');

if (fs.existsSync(packageJsonPath)) {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
    const deps = { ...packageJson.dependencies, ...packageJson.devDependencies };

    if (deps['@supabase/supabase-js']) {
        console.log(`  ✅ @supabase/supabase-js installed (${deps['@supabase/supabase-js']})`);
    } else {
        console.log('  ❌ @supabase/supabase-js not installed');
        allChecksPass = false;
    }

    if (deps['@supabase/ssr']) {
        console.log(`  ✅ @supabase/ssr installed (${deps['@supabase/ssr']})`);
    } else {
        console.log('  ❌ @supabase/ssr not installed');
        allChecksPass = false;
    }
} else {
    console.log('  ❌ package.json not found');
    allChecksPass = false;
}

// Summary
console.log('\n' + '='.repeat(60));
console.log('\n📊 Summary\n');

if (allChecksPass) {
    console.log('✅ All local checks passed!');
    console.log('\n📝 Next Steps:');
    console.log('  1. Get Google OAuth credentials from Google Cloud Console');
    console.log('  2. Add credentials to Supabase Dashboard');
    console.log('  3. Configure redirect URLs in Google Console');
    console.log('  4. Test the authentication flow');
    console.log('\n📚 See SUPABASE_GOOGLE_OAUTH_SETUP.md for detailed instructions');
} else {
    console.log('❌ Some checks failed. Please review the errors above.');
    console.log('\n💡 Tip: Make sure you have run npm install and all files are in place.');
}

console.log('\n' + '='.repeat(60) + '\n');

// Manual Configuration Checklist
console.log('⚙️  Manual Configuration Checklist:\n');
console.log('  [ ] Created Google OAuth Client ID in Google Cloud Console');
console.log('  [ ] Added Google Client ID to Supabase Dashboard');
console.log('  [ ] Added Google Client Secret to Supabase Dashboard');
console.log('  [ ] Configured redirect URL in Google Console:');
console.log('      https://tmloozpmxffxfitxnofo.supabase.co/auth/v1/callback');
console.log('  [ ] Enabled Google provider in Supabase Dashboard');
console.log('  [ ] Tested login flow');
console.log('  [ ] Tested signup flow');
console.log('\n');
