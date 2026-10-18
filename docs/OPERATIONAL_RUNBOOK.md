# 📖 Ele-in Platform — Production Operational Runbook

**Current Status:** Pre-Commercial Launch & Staging Verification  
**Target Architecture:** FastAPI (Python 3.9+) + React (Vite 8, Tailwind v4, Radix UI) + Supabase (PostgreSQL 15)  
**Last Updated:** October 2026

---

## 1. System Architecture & Service Topology

The Ele-in platform is decoupled into four primary runtime services:

```
                      ┌────────────────────────────┐
                      │    Cloudflare / Reverse    │
                      │           Proxy            │
                      └─────────────┬──────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │                                         │
        [/* (SPA Assets)]                       [/api/* (REST Calls)]
               ▼                                         ▼
   ┌───────────────────────┐                 ┌───────────────────────┐
   │    Vite Production    │                 │   FastAPI Web Core    │
   │      Static Edge      │                 │    (Port 8000)        │
   │  (dist/ 165kB entry)  │                 │  (411 Route Endpoints)│
   └───────────────────────┘                 └───────────┬───────────┘
                                                         │
                             ┌───────────────────────────┴───────────────────────────┐
                             ▼                                                       ▼
                ┌───────────────────────────┐                           ┌───────────────────────────┐
                │  Background Worker Pool   │                           │     Supabase / Postgres   │
                │ • job_processor           │                           │ • 96 Relational Tables    │
                │ • orchestrator_worker     │                           │ • 54 RLS Policies         │
                │ • webhook_worker (DLQ)    │                           │ • PostgREST API Engine    │
                │ • outbox_worker (Jitter)  │                           └───────────────────────────┘
                └───────────────────────────┘
```

---

## 2. Container Health & Readiness Probes

All container orchestrators (Kubernetes, AWS ECS/EKS, Docker Swarm, Fly.io, Render) and load balancers must be configured using these verified unauthenticated probe endpoints:

### Liveness Probes
- **Endpoints**: `GET /health` or `GET /api/health`
- **Authentication**: Unauthenticated (Open)
- **Response**: HTTP `200 OK`
- **Payload**:
  ```json
  {
    "status": "healthy",
    "service": "ele-in-backend",
    "version": "3.0.0",
    "environment": "production",
    "timestamp": "2026-10-18T06:20:00.000000+00:00"
  }
  ```
- **Behavior**: Zero database or external I/O. Fails only if the uvicorn event loop is blocked or dead.

### Readiness Probes
- **Endpoints**: `GET /ready` or `GET /api/ready`
- **Authentication**: Unauthenticated (Open)
- **Healthy Response**: HTTP `200 OK`
  ```json
  {
    "status": "ready",
    "database": "connected",
    "service": "ele-in-backend",
    "version": "3.0.0",
    "timestamp": "2026-10-18T06:20:00.000000+00:00"
  }
  ```
- **Degraded Response**: HTTP `503 Service Unavailable`
  ```json
  {
    "status": "degraded",
    "database": "unreachable",
    "service": "ele-in-backend",
    "version": "3.0.0",
    "error": "Connection pool timeout",
    "timestamp": "2026-10-18T06:20:00.000000+00:00"
  }
  ```
- **Recommended Kubernetes Probe Spec**:
  ```yaml
  livenessProbe:
    httpGet:
      path: /health
      port: 8000
    initialDelaySeconds: 5
    periodSeconds: 10
    timeoutSeconds: 2
    failureThreshold: 3
  readinessProbe:
    httpGet:
      path: /ready
      port: 8000
    initialDelaySeconds: 10
    periodSeconds: 15
    timeoutSeconds: 3
    failureThreshold: 2
  ```

---

## 3. Environment Variables Master Matrix

| Variable Name | Required | Default | Purpose & Security Scope |
| :--- | :---: | :---: | :--- |
| `ENVIRONMENT` | Yes | `production` | Deployment mode (`production`, `staging`, `development`). Controls CORS strictness and error masking. |
| `ALLOWED_ORIGINS` | No | *See Section 4* | Comma-separated CORS allowed domains (e.g. `https://app.ele-in.com,https://ele-in.com`). |
| `RATE_LIMIT_DEFAULT` | No | `300/minute` | SlowAPI default sliding window limit per client IP. |
| `SUPABASE_URL` | Yes | - | Full HTTPS URL of Supabase project. |
| `SUPABASE_SERVICE_KEY` | Yes | - | Elevated service-role key for background daemons and internal RPCs. |
| `SUPABASE_JWT_SECRET` | Yes | - | Secret string used to verify user JWTs in `auth_dep.py`. |
| `SENTRY_DSN` | No | - | Sentry project DSN for error telemetry and performance tracing. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.2` | Floating-point sample rate clamped between `0.0` and `1.0`. |
| `RAZORPAY_KEY_ID` | Yes | - | Razorpay live API key ID. |
| `RAZORPAY_KEY_SECRET` | Yes | - | Razorpay live API secret. |
| `RAZORPAY_WEBHOOK_SECRET` | Yes | - | Shared secret used to verify Razorpay webhook HMAC SHA-256 signatures. |
| `ENCRYPTION_KEY` | Yes | - | 32-byte Fernet key used to encrypt LinkedIn session cookies at rest. |
| `METRICS_TOKEN` | Yes | - | Bearer token required to scrape `/metrics` Prometheus endpoint. |

---

## 4. Security Architecture & Edge Hardening

### Enterprise Security Headers
Injected into 100% of HTTP responses via `core/backend/core/security.py`:
- `Strict-Transport-Security`: `max-age=31536000; includeSubDomains; preload`
- `X-Content-Type-Options`: `nosniff`
- `X-Frame-Options`: `DENY`
- `X-XSS-Protection`: `1; mode=block`
- `Referrer-Policy`: `strict-origin-when-cross-origin`
- `Permissions-Policy`: `accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(self), payment=(self), usb=()`
- `Cross-Origin-Opener-Policy`: `same-origin-allow-popups`
- `Cross-Origin-Resource-Policy`: `cross-origin`

### Spoofing-Defended Rate Limiting
- **IP Resolution Order**: `CF-Connecting-IP` → `X-Real-IP` → `X-Forwarded-For` (first valid IP) → `request.client.host`.
- Every candidate is validated against `ipaddress.ip_address()` with port-stripping defense to prevent header injection attacks.

### CORS & Credentials Isolation
- When `ENVIRONMENT=production`, defaults to official domains (`https://ele-in.com`, `https://app.ele-in.com`, `https://elein.in`, `https://app.elein.in`).
- If explicit domains are used, `allow_credentials=True` is safely granted.
- If wildcard `*` is present, `allow_credentials=False` is enforced to prevent browser credential leakage.

---

## 5. Startup, Shutdown & Self-Healing Protocol

### Starting the Production Backend
**Always use `./backend/start.sh`** rather than invoking uvicorn directly:
```bash
./backend/start.sh
```
**What `./backend/start.sh` does automatically:**
1. Scans for orphaned Python/uvicorn processes holding port 8000 (`lsof -ti :8000 | xargs kill -9`).
2. Kills previous dead worker instances (`job_processor`, `orchestrator_worker`).
3. Launches background workers via `./backend/start-worker.sh`.
4. Runs pending database migrations via `backend/scripts/apply_migrations.py`.
5. Starts uvicorn on `0.0.0.0:8000`.
6. Traps termination signals and gracefully cleans up worker subprocesses upon exit.

---

## 6. Incident Response & Troubleshooting Playbook

### Incident 1: API Returns 502 Bad Gateway
- **Symptom**: Frontend displays `502 Bad Gateway` on save or API requests.
- **Root Cause**: Orphaned ghost workers holding port 8000 while uvicorn master process crashed.
- **Remediation**:
  ```bash
  lsof -ti :8000 | xargs kill -9
  ./backend/start.sh
  ```

### Incident 2: Frontend Displays "Backend Unavailable (503)"
- **Symptom**: Vite proxy or API gateway returns 503 with `"BACKEND_UNAVAILABLE"`.
- **Root Cause**: Backend service is stopped or restarting.
- **Remediation**: Check backend log output:
  ```bash
  tail -f logs/backend.log
  ```
  Ensure `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are reachable and valid.

### Incident 3: Readiness Probe Alerts 503 Degraded
- **Symptom**: Container orchestrator marks pods as unready; `/ready` returns 503.
- **Root Cause**: PostgREST connection to Supabase timed out or database connection pool is saturated.
- **Remediation**:
  1. Inspect Supabase dashboard metrics (Pool connection percentage).
  2. Verify no long-running unindexed transaction is locking rows (`SELECT pid, query, state, age(clock_timestamp(), query_start) FROM pg_stat_activity WHERE state != 'idle';`).
  3. Probes will automatically recover to HTTP 200 as soon as PostgREST connectivity is restored.

### Incident 4: Outbox Webhook Deliveries Failing
- **Symptom**: Webhooks or in-app notifications are stuck in `pending`.
- **Root Cause**: Downstream client endpoint is offline or returning 5xx.
- **Remediation**:
  1. `outbox_worker` and `webhook_worker` automatically apply exponential backoff with randomized jitter (Attempt 1: 60s, Attempt 2: 120s, Attempt 3+: 300s).
  2. Deliveries exceeding max retry count are moved to the Dead Letter Queue (DLQ) with status `failed`.
  3. Admins can replay failed deliveries directly from the Outbound Webhook Studio on `/elein/integrations`.

---

## 7. Zero-Downtime Deployment Verification Checklist

Before landing any new release to production:

- [ ] 1. **Database Sync**: Ensure migrations have been executed in Supabase.
- [ ] 2. **TypeScript Compilation**: Run `npx tsc -b` (must exit with code 0).
- [ ] 3. **Vite Production Build**: Run `npm run build` (must build cleanly with 0 warnings).
- [ ] 4. **Smoke Suite Pass**: Run `./backend/venv/bin/pytest campaigns/backend/tests/test_preflight_production_smoke.py -v` (8/8 passing).
- [ ] 5. **Paranoia Engine Pass**: Run `./backend/venv/bin/pytest campaigns/backend/tests/test_stage6_paranoia_remediation.py -v` (9/9 passing).
- [ ] 6. **Container Health Probes**: Verify `/health` returns 200 and `/ready` returns 200.
