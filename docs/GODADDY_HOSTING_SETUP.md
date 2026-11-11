# Connecting Your GoDaddy Domain to Ele-in

This runbook guides you through connecting your GoDaddy domain (`ele-in.com`) to the Ele-in waitlist and platform.

---

## Option 1 (Easiest): GitHub Pages + Direct Supabase Serverless

Because the Ele-in waitlist now includes a **Three-Layer Serverless Bridge** ([`waitlistApi.ts`](file:///Users/krdeeksha/Ele-in/core/frontend/lib/waitlistApi.ts)), you can host the entire public waitlist on **GitHub Pages for $0/month** with zero backend server running! Signups bypass the backend automatically and persist straight to your Supabase `waitlist` table.

### Step 1: GoDaddy DNS Settings for GitHub Pages
Log in to [GoDaddy Domain Portfolio](https://dcc.godaddy.com/domains) -> click **DNS** on `ele-in.com`:

1. Click **Edit** (pencil icon) on the existing `a | @ | Parked` row and enter the first IP below, then add the other 3 A records for `@`:
   - `185.199.108.153`
   - `185.199.109.153`
   - `185.199.110.153`
   - `185.199.111.153`
2. Click **Edit** (pencil icon) on the existing `cname | www | ele-in.com.` row and replace the value with:
   - **`655chaman.github.io`**
3. Save all changes.

### Step 2: Run the SQL Migration in Supabase
Copy and run [`backend/migrations/20261110_create_waitlist.sql`](file:///Users/krdeeksha/Ele-in/backend/migrations/20261110_create_waitlist.sql) inside your **Supabase Dashboard -> SQL Editor**. This creates the `public.waitlist` table, public RLS policies, and the `increment_waitlist_referral` RPC function.

### Step 3: Enable GitHub Pages on Repository
1. Push your branch to GitHub (`git push origin main`).
2. In your GitHub repo (`655Chaman/ELE-IN`) -> **Settings** -> **Secrets and variables** -> **Actions** -> Add two Repository Variables:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
3. In GitHub **Settings** -> **Pages**:
   - Under **Build and deployment -> Source**, select **GitHub Actions**.
   - Under **Custom domain**, type **`ele-in.com`** and check **Enforce HTTPS**.
4. The workflow [`.github/workflows/deploy-gh-pages.yml`](file:///Users/krdeeksha/Ele-in/.github/workflows/deploy-gh-pages.yml) automatically builds and deploys `dist/` with `CNAME` and `404.html` SPA support!

---

## Option 2: Architecture Overview (Full-Stack App + Workers)

```
                      ┌─────────────────────────────────┐
                      │    GoDaddy DNS Management       │
                      │         (ele-in.com)            │
                      └────────────────┬────────────────┘
                                       │
                ┌──────────────────────┴──────────────────────┐
                │                                             │
      [@ & www (A/CNAME)]                              [api (CNAME)]
                ▼                                             ▼
    ┌───────────────────────────┐                 ┌───────────────────────────┐
    │     Frontend Edge Host    │                 │    FastAPI Backend Host   │
    │      (Vercel / Render)    │                 │       (Render / Fly)      │
    │   • Public Waitlist (/)   │                 │ • Waitlist API (/api/...) │
    │   • Protected App (/elein)│                 │ • Billing & Auth Engine   │
    │   • Member Login (/login) │                 │ • Lead Enrichment Workers │
    └───────────────────────────┘                 └─────────────┬─────────────┘
                                                                │
                                                                ▼
                                                  ┌───────────────────────────┐
                                                  │    Supabase PostgreSQL    │
                                                  │   • waitlist table        │
                                                  │   • EARLY30 30% coupons   │
                                                  └───────────────────────────┘
```

---

## 2. Step-by-Step GoDaddy DNS Setup

Log in to your [GoDaddy Domain Portfolio](https://dcc.godaddy.com/domains) and click **DNS** next to your domain.

### Option A: Recommended Hosting (Vercel Edge for Frontend + Render for Backend)

Vercel provides instant global CDN, automatic free SSL certificates, and zero-cost bandwidth for your waitlist and frontend.

1. **In GoDaddy DNS Records**, add/edit these records:

| Type | Name (Host) | Value (Points to) | TTL | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **A** | `@` | `76.76.21.21` | 1/2 Hour | Directs root `ele-in.com` to Vercel |
| **CNAME** | `www` | `cname.vercel-dns.com` | 1/2 Hour | Directs `www.ele-in.com` to Vercel |
| **CNAME** | `api` | `elein-backend.onrender.com` | 1/2 Hour | Directs `api.ele-in.com` to Backend |

2. **Deploying the Frontend to Vercel (1-Click)**:
   - Go to [Vercel](https://vercel.com) -> **Add New Project** -> Import your Ele-in GitHub repo.
   - Vercel will automatically detect `vercel.json` (already pre-configured in this repository).
   - Under **Environment Variables**, add:
     - `VITE_API_URL`: `https://api.ele-in.com`
     - `VITE_SUPABASE_URL`: `https://cztwrosldjrichuwdpxu.supabase.co`
     - `VITE_SUPABASE_ANON_KEY`: *(From backend/.env)*
   - Click **Deploy**.
   - In Vercel Project Settings -> **Domains** -> Add `ele-in.com` and `www.ele-in.com`. Vercel automatically verifies GoDaddy DNS and provisions the SSL certificate within 2-5 minutes.

---

### Option B: All-in-One Render Deployment (Using `render.yaml`)

This repository already contains a unified [`render.yaml`](file:///Users/krdeeksha/Ele-in/render.yaml) specification that provisions:
- `elein-frontend` (Vite static SPA)
- `elein-backend` (FastAPI Web Service on Port 8000)
- `elein-worker` (Background Celery/Multiprocess Runner)

1. In Render Dashboard: Click **New +** -> **Blueprint** -> Select this repository.
2. Render creates all three services automatically.
3. In `elein-frontend` settings -> **Custom Domains** -> Add `ele-in.com` and `www.ele-in.com`.
4. Render will provide its A Record and CNAME to paste into GoDaddy:
   - **A Record**: `@` -> `216.24.57.1`
   - **CNAME Record**: `www` -> `elein-frontend.onrender.com`
   - **CNAME Record**: `api` -> `elein-backend.onrender.com`

---

## 3. The 30% First-Year Discount Configuration

When waitlist members sign up, the system automatically registers them for the **EARLY30** promotion:

- **Discount Code**: `EARLY30`
- **Benefit**: 30% off all plans (Starter, Growth, Agency) for the entire first 12 months.
- **Pricing Impact**:
  - **Starter Tier**: $29/mo -> **$20.30/mo**
  - **Growth Tier**: $99/mo -> **$69.30/mo** (Annual: $948/yr -> **$663.60/yr**)
  - **Agency Tier**: $249/mo -> **$174.30/mo** (Annual: $2,390/yr -> **$1,673/yr**)
- **Automated Validation Endpoint**:
  ```bash
  POST /api/elein/billing/coupons/validate
  {
    "coupon_code": "EARLY30",
    "package_id": "growth_tier"
  }
  ```
  Returns validated 30% discount calculations and updates checkout order creation in Razorpay / LemonSqueezy.

---

## 4. Verification Checklist

- [ ] GoDaddy DNS: `@` points to host IP, `www` points to frontend CNAME.
- [ ] GoDaddy DNS: `api` points to backend host CNAME.
- [ ] Visit `https://ele-in.com/`: Waitlist landing page loads with zero console errors.
- [ ] Submit a test email: Position assigned, referral link generated, `EARLY30` voucher locked.
- [ ] Visit `https://ele-in.com/login`: Existing member login page loads cleanly.
- [ ] Visit `https://ele-in.com/elein/admin`: Admin can view waitlist entrants and export CSV.
