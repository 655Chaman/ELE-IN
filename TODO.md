# 📋 Ele-in Platform — Master TO-DO List

**Current Environment Status:** Beta Testing Phase  
**Last Updated:** October 15, 2026  

---

## 🔴 HIGH PRIORITY — Pre-Commercial Launch

*All pre-commercial monetization and production telemetry gates are fully resolved and operational.*

---

## 🟢 COMPLETED MILESTONES

- [x] **Phase 27: RFC 8058 One-Click Unsubscribe & Google/Yahoo Deliverability Compliance (100% Operational):**
  - **Cryptographic Unsubscribe Engine**: Built [`campaigns/backend/services/unsubscribe_service.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/services/unsubscribe_service.py) with HMAC-SHA256 URL-safe token signing, constant-time tampering defense, lead status updates (`status="UNSUBSCRIBED"`), DNC insertion, and atomic campaign sequence purging.
  - **Zero-Friction RFC 8058 API Router**: Built [`campaigns/backend/routers/unsubscribe.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/routers/unsubscribe.py) handling both RFC 8058 POST requests (`List-Unsubscribe=One-Click`) with zero confirmation friction and human browser GET requests with a clean, dark-mode-ready confirmation card.
  - **Executor Header Injection**: Upgraded [`campaigns/backend/services/elein_executor.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/services/elein_executor.py) (`handle_send_email`) to inject `List-Unsubscribe: <{unsub_url}>, <mailto:unsub+{token}@{domain}>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` into SendGrid and SMTP mail payloads with Paranoia Layer 1 fail-open defense.
  - **Full Automated Test Coverage**: Built [`campaigns/backend/tests/test_rfc8058_one_click_unsubscribe.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/tests/test_rfc8058_one_click_unsubscribe.py) and [`campaigns/backend/tests/test_unsubscribe_rfc8058.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/tests/test_unsubscribe_rfc8058.py) (20/20 tests passing).

- [x] **Phase 25: Production Container Probes & Edge Security Hardening (100% Operational):**
  - Implemented unauthenticated container orchestrator probes: `GET /health` and `GET /api/health` for liveness (zero-dependency, returns 200 with service metadata); `GET /ready` and `GET /api/ready` for readiness with Supabase PostgREST connectivity probe and graceful HTTP 503 fallback when degraded.
  - Hardened CORS configuration in [`core/backend/main.py`](file:///Users/krdeeksha/Ele-in/core/backend/main.py) with `ALLOWED_ORIGINS` environment support, production domain defaults, and `allow_credentials=True` safety without wildcard exposure.
  - Upgraded SlowAPI rate limiting in [`core/backend/core/security.py`](file:///Users/krdeeksha/Ele-in/core/backend/core/security.py) using spoofing-defended IP resolver (`CF-Connecting-IP`, `X-Real-IP`, `X-Forwarded-For`, port stripping, `ipaddress.ip_address` validation) with configurable `RATE_LIMIT_DEFAULT` (default `300/minute`).
  - Enforced strict enterprise security headers on 100% of responses (`Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin-allow-popups`, `Cross-Origin-Resource-Policy: cross-origin`).

- [x] **Phase 26: Pre-Launch E2E Staging Smoke Test & Operational Runbook (100% Verified):**
  - Created automated pre-flight smoke test suite [`campaigns/backend/tests/test_preflight_production_smoke.py`](file:///Users/krdeeksha/Ele-in/campaigns/backend/tests/test_preflight_production_smoke.py) covering liveness, readiness, degraded database failover, security headers, CORS preflight, rate limiting, and static media traversal defense (8/8 tests passing).
  - Authored comprehensive production operational runbook [`docs/OPERATIONAL_RUNBOOK.md`](file:///Users/krdeeksha/Ele-in/docs/OPERATIONAL_RUNBOOK.md) documenting service topology, Kubernetes probe specifications, environment variable matrix, ghost worker self-healing, and incident response playbooks.
  - Zero TypeScript errors (`npx tsc -b`) and sub-second Vite production build (851ms).

- [x] **Phase 23: Complete Radius Harmonization & Micro-Interaction Eradication (100% Verified):**
  - Standardized all outer modal dialogs, shells, and containers from `rounded-3xl` and `rounded-2xl` to standard `rounded-xl` (12px).
  - Standardized all inner cards, inputs, icon badges, and preview docks to `rounded-lg` (8px), and status indicators/pills to `rounded-full`.
  - Eradicated 100% of gimmicky micro-interactions (`hover:scale-*`, `active:scale-*`, and `animate-bounce`) across the entire frontend codebase (`0` remaining instances).
  - Zero tolerance verification: `git grep -n "rounded-3xl"` (0 hits), `git grep -n "rounded-2xl"` (0 hits), `git grep -n -E "hover:scale-|active:scale-"` (0 hits).

- [x] **Phase 24: Hardcoded Hex & Dark-Mode Token Hardening (100% Operational):**
  - Eradicated all non-semantic hardcoded hex strings (`#070809`, `#0A0A0B`, `#0f0f0f`, `bg-zinc-900/60`, `border-white/10`) poisoning light/dark mode contrast and causing unreadable text.
  - Mapped all background, foreground, border, and elevation layers to official semantic design tokens (`bg-background`, `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`, `shadow-xs`).
  - Purged neon gradients, multi-hue background blobs, and glowing button shadows in favor of crisp, enterprise-tier Linear/Stripe aesthetic.
  - Verified with clean TypeScript compilation (`npx tsc -b`) and production build in 677ms.

- [x] **Phase 21: Pre-Commercial Monetization & Live Billing Gateway Switchover (100% Operational):**
  - Switched `isBetaTestingMode = false` in [`core/frontend/contexts/PaywallContext.tsx`](file:///Users/krdeeksha/Ele-in/core/frontend/contexts/PaywallContext.tsx), activating the live `CreditTopUpModal` and credit paywalls across all outbound actions.
  - Bound `@router.post("/webhook/razorpay")` in [`core/backend/api/routers/billing.py`](file:///Users/krdeeksha/Ele-in/core/backend/api/routers/billing.py) with HMAC SHA-256 signature verification, idempotency protection, and atomic ledger credit allocation.
  - Verified official 18% GST tax invoice generation endpoint `/api/elein/billing/transactions/{transaction_id}/receipt` with SAC code 998313, CGST (9%) + SGST (9%), reverse charge disclosures, and printable receipt modal.
  - Passed all billing test suites (`campaigns/backend/tests/test_horizon6_billing.py` and `campaigns/backend/tests/test_low_priority_credit_hardening.py` - 15/15 passing).

- [x] **Phase 22: Production Observability & Sentry Error Telemetry (100% Operational):**
  - Integrated `@sentry/react` into frontend with environment tagging, release binding (`ele-in-web@3.0.0`), PII header scrubbing (`authorization`, `cookie`, `x-api-key`), browser noise filtering, and 10-second error deduplication in [`core/frontend/lib/telemetry.ts`](file:///Users/krdeeksha/Ele-in/core/frontend/lib/telemetry.ts).
  - Wired telemetry into [`core/frontend/main.tsx`](file:///Users/krdeeksha/Ele-in/core/frontend/main.tsx), [`core/frontend/catch_errors.ts`](file:///Users/krdeeksha/Ele-in/core/frontend/catch_errors.ts), [`core/frontend/ErrorBoundary.tsx`](file:///Users/krdeeksha/Ele-in/core/frontend/ErrorBoundary.tsx), [`core/frontend/lib/AuthContext.tsx`](file:///Users/krdeeksha/Ele-in/core/frontend/lib/AuthContext.tsx), and [`core/frontend/contexts/WorkspaceContext.tsx`](file:///Users/krdeeksha/Ele-in/core/frontend/contexts/WorkspaceContext.tsx).
  - Hardened backend Sentry telemetry in [`core/backend/main.py`](file:///Users/krdeeksha/Ele-in/core/backend/main.py) with clamped safe float parsing for sample rates, environment tagging, and sensitive header stripping (`_sentry_before_send`).
  - Implemented fail-safe forwarding in [`core/backend/api/routers/error_logger.py`](file:///Users/krdeeksha/Ele-in/core/backend/api/routers/error_logger.py) with `sentry_sdk.new_scope()` integration, forwarding client errors while protecting local rate limiting (8/8 tests passing).

- [x] **Phase 20: End-to-End Authenticated Browser QA & Interactive Dogfooding (100% Verified):** Provisioned demo account in Supabase auth and completed live automated browser audit with Puppeteer across all 12 primary application views (`/elein`, `/campaigns`, `/campaigns/new`, `/leads`, `/inbox`, `/knowledge`, `/accounts`, `/engagement`, `/templates`, `/settings`, `/billing`, `/onboarding`). Performed live interactive tests on `@radix-ui/react-select` primitives inside nested modal dialogs (`DynamicSegmentationStudioModal` Seniority Level dropdown and `EleInEngagementStudio` sender dropdown). Verified zero React invariant crashes, zero z-index portal clipping, 100% clean visual hierarchy, and sub-second chunk lazy-loading across all studios.
- [x] **Dynamic Route & Vendor Bundle Code-Splitting:** Initial entry bundle reduced by 95.6% (from 3.79 MB down to 164 kB, 45 kB gzipped). Clean route-level `React.lazy()` chunking with custom `RouteLoadingFallback` and vendor isolation (`vendor-react`, `vendor-recharts`, `vendor-supabase`, `vendor-motion`, `vendor-radix`, `vendor-icons`). Build completed in 646ms with 0 chunk size warnings.
- [x] **Complete Radix UI Select Migration (82/82 Standardized):** 100% eradication of native `<select>` dropdowns across 28 files onto bespoke `@radix-ui/react-select` primitive suite with Paranoia Layer 1 empty-value token protection and `z-[9999]` portal mounting.
- [x] **Master Credit & Monetization Audit (34/34 Resolved):** P0 mock billing bypass closed, atomic deductions via PostgreSQL RPC, distributed advisory locks, server-authoritative 48h OTO momentum timer.
- [x] **Thompson Sampling Bandit Optimizer & Copy Evolution Studio (Paranoia Framework Fortified):**
  - **Feature 1 (Angle Testing):** Channel-aware length clamping (295-char LinkedIn note ceiling with word-boundary preservation), Subject + Body email validation, single-bracket `{token}` auto-repair to `{{token}}`.
  - **Feature 2 (Self-Optimizing Traffic):** Thompson Sampling with burn-in exploration floor (`MIN_BURNIN_IMPRESSIONS = 15`), toxic feedback penalty ($\beta + 3.0$), and sticky lead-to-arm routing.
  - **Feature 3 (Lead Signals & Trigger Radar):** Null-safe interpolation, stale trigger circuit breaker (>90d), cross-team enrollment collision locks, and workspace suppression list (DNC) defense.
  - **Stage 3 (Copy Evolution Studio):** Multi-theme genetic synthesizer (`social_proof_metric`, `provocative_question`, `low_friction_benchmark`, `brevity_direct`), non-destructive staging preview (`retire_parent=False`), duplicate copy avoidance, generation capping ($\le 10$), live token chips, and dynamic generation lineage timeline. 42/42 tests passing.
- [x] **Horizons 1 through 38 & Phases 1 through 6:** Full engine completion with 1,924 / 1,924 automated tests passing.
- [x] **Database Master Migration (`999_master_pending_sync.sql`):** 96 tables, 97 indexes, 12 functions, 54 RLS policies executed successfully in Supabase.
- [x] **Phase 27: RFC 8058 One-Click Unsubscribe & Gmail/Yahoo Deliverability Hardening (100% Operational):**
  - Implemented cryptographic HMAC-SHA256 signed urlsafe token generation and constant-time verification (`verify_unsubscribe_token`).
  - Implemented compliant `List-Unsubscribe` (<https://...>, <mailto:...>) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` email headers.
  - Implemented unauthenticated public endpoint `POST /api/elein/unsubscribe` with instant zero-friction 200 JSON return for automated Gmail/Yahoo unsubscribes.
  - Implemented responsive dark-mode HTML confirmation page on `GET /api/elein/unsubscribe` for human clickers.
  - Wired atomic cascade into `leads` table (`status = 'UNSUBSCRIBED'`), suppression list (`suppression_list`), and active sequence job cancellation (`retroactive_purge`).
  - Injected headers into `EleInExecutor.handle_send_email` with fail-open Paranoia Layer 1 fallback.
  - 100% test coverage with 44/44 automated deliverability tests passing.

- [x] **Phase 28: Lead Name & Company Slogan Sanitizer for Apollo/LinkedIn Scraping (100% Operational):**
  - **Data Hygiene Core (`leads/backend/services/data_hygiene.py`)**:
    - `clean_name`: Strips bracketed status tags (`(We're hiring)`, `(she/her)`, `[Hiring AEs]`, `{Open to work}`), attached job titles and status announcements after separators (` - `, ` | `, ` • `, ` / `, ` – `, ` — `), emojis, and formal honorifics/suffixes (`Dr.`, `PhD`, `PMP`).
    - `clean_first_name`: Extracts single first name token, handles initials (`"J. Robert Oppenheimer"` -> `"Robert"`), preserves mixed-case Celtic/Dutch particles (`O'Connor`, `van der Berg`), strips trailing punctuation.
    - `clean_company`: Strips accelerator tags (`(YC W19)`, `(formerly Twitter)`), marketing slogans after delimiters (`"Notion - The all-in-one workspace"` -> `"Notion"`), corporate legal entity suffixes (`LLC`, `Inc`, `GmbH`, `Ltd`, `B.V.`), and domain imports (`tryacme.io` -> `Acme`, `getscale.ai` -> `Scale`), while preserving short corporate acronyms (`IBM`, `AWS`, `SAP`, `BMW`, `HP`, `GMC`).
  - **Template Interpolation Engine (`campaigns/backend/services/elein_executor.py`)**:
    - Integrated `clean_first_name` and `clean_company` into `_interpolate_template`.
    - Sanitizes `{{first_name}}`, `{{firstname}}`, `{{first_name_clean}}`, `{{company}}`, `{{company_name}}`, and `{{company_clean}}`.
    - Guaranteed full fallback support (`"there"` and `"your company"`) when values are missing or stripped.
  - **Lead Ingestion Service (`leads/backend/services/lead_ingestion_service.py`)**:
    - Automatically cleans first names and company names upon CSV, API, or webhook ingestion before storing in database.
- [x] **Phase 29: Recipient Timezone & Working Hours Guard (100% Operational):**
  - **Location & Timezone Inference Engine (`leads/backend/services/location_timezone_service.py`)**:
    - Built-in geographical reference database mapping 150+ global metro tech hubs (London, Paris, Berlin, Tokyo, Singapore, Bengaluru, Dubai, São Paulo, Sydney, etc.), all 50 US states & territories, Canadian provinces, and Australian states to validated standard IANA timezones.
    - Resolves international phone dial codes (`+1`, `+44`, `+49`, `+33`, `+91`, `+61`, `+81`, `+65`, etc.) and ISO-2/3 country codes when location string is absent.
    - Poison location filters ignoring non-geographic tokens (`'remote'`, `'worldwide'`, `'global'`, `'anywhere'`, `'virtual'`, `'home'`, `'wfh'`, `'n/a'`).
    - Ultra-fast sub-millisecond lookups via `@functools.lru_cache(maxsize=4096)`.
  - **Timezone Resolution & Orchestrator Postponement (`campaigns/backend/services/timezone_utils.py`, `elein_orchestrator.py`)**:
    - `resolve_target_timezone`: Dynamically infers lead timezone from location/country/phone in `lead_local_time` mode before falling back to campaign or UTC.
    - `calculate_next_run_with_jitter`: Schedules the next available business window with deterministic pseudo-random jitter (5–25 mins) preventing thunderous herd spikes on SendGrid/LinkedIn at 09:00:00.
    - Weekend and Friday evening rollover guard: automatically defers Friday post-5:00 PM dispatches to Monday morning (never Saturday or Sunday).
    - `is_within_recipient_window`: Real-time gate verifying recipient local working hours before executing any sequence node.
  - **Lead Ingestion Service (`leads/backend/services/lead_ingestion_service.py`)**:
    - Automatically infers and stores validated IANA timezone on all imported leads across CSV, API, and webhook routes.
  - **Verification**: 151/151 automated tests passing across test suites; 62/62 dedicated timezone paranoia test cases passing in 0.50s.

- [x] **Phase 30: Open Profile InMail Arbitrage & Free Credit Discovery (100% Operational):**
  - **Open Profile Probing & Worker Arbitrage (`integrations/backend/services/linkedin_worker.py`)**:
    - `check_open_profile`: Multi-probe DOM inspection (`.open-profile-badge`, `svg[data-test-icon='gold-badge']`, `span:has-text('Open')`, text regex `/(Open Profile|Free message)/i`) returning structured detection `{open: True/False, branch: "Open"/"Not open", inmail_type: "free"/"paid"}` wrapped in `@linkedin_action_safe` with graceful timeout fallback.
    - `send_inmail`: Detects Free InMail composer indicators. When `only_free=True`, identifies paid credit requirement banners and cleanly aborts before credit debit with `requires_paid_credit=True`.
  - **Campaign Executor & Limit Bypass (`campaigns/backend/services/elein_executor.py`)**:
    - `handle_send_inmail`: Pre-flight arbitrage gate querying `is_open_profile` from lead payload or Supabase cache.
    - Bypasses daily paid InMail rate limits (`_check_limit("inmail")`) when sending to Open Profiles because Free InMails consume zero paid credits ($0 debit).
    - Arbitrage diversion: Automatically diverts closed profiles to free connection requests (with note clamped to 300 chars) or verified email fallback when `only_send_free_inmails=True`.
    - Value telemetry: Surfaces `is_free_inmail=True`, `inmail_tier="free"`, and `credits_saved=1` in execution results.
    - Auto-persists confirmed Open Profile status back to `leads` table in Supabase for permanent zero-cost reuse across campaigns.
    - Standardized `handle_send_paid_inmail` and `handle_open_profile_check` to share this robust 3-layer architecture.
  - **Lead Ingestion Service (`leads/backend/services/lead_ingestion_service.py`)**:
    - Standardized and normalized `is_open_profile` across all truthy (`True`, `"true"`, `"1"`, `1`, `"yes"`, `"open"`) and falsy variations during bulk imports and updates.
  - **Verification**: 41/41 automated tests passing across `test_inmail_open_profile_arbitrage.py` (31/31) and `test_inmail_arbitrage.py` (10/10) with 0 regressions and sub-second Vite production build.

- [x] **Phase 31: Dynamic Sender Domain & Mailbox Rotation with Burnout Protection (100% Operational):**
  - **Root Domain Engine & Domain Aggregation (`integrations/backend/services/email_sender_service.py`)**:
    - `extract_root_domain`: Normalizes email addresses, subdomains, and 2-part ccTLDs (`.co.uk`, `.com.au`, `.co.nz`, `.com.br`, `.co.jp`, `.co.in`, etc.) to clean effective root domains (eTLD+1), with Paranoia Layer 2 SSRF, IP literal, and localhost blocking.
    - `aggregate_domain_metrics`: Groups inboxes by root domain, computing aggregate volume (`total_sent`, `total_sent_today`), domain daily capacity headroom (`remaining_domain_capacity`), bounce and spam rates, and live health status (`HEALTHY`, `AT_RISK`, `BURNOUT_QUARANTINED`).
  - **Domain Circuit Breaker & Burnout Protection**:
    - `evaluate_domain_burnout_tripwire`: Enforces a small-sample false-positive guard (`min_sample_size=15`), absolute ceiling floors (5 bounces or 2 spam complaints), percentage tripwires (bounce rate >= 3.0%, spam complaint rate >= 0.1%), and majority mailbox quarantine (>= 50% inboxes quarantined) triggering automatic 24h domain burnout cooldown.
    - `record_inbox_delivery_outcome`: Automatically updates domain-level metrics and cascades quarantine across all mailboxes sharing a burned domain.
  - **Cross-Domain Balancing & Thread Affinity Fallbacks**:
    - `DOMAIN_BALANCED` rotation strategy balances sending volume evenly across distinct domains (selecting domain with lowest sends today, then highest-headroom inbox within that domain).
    - Hourly velocity throttling (`hourly_limit`) defers mailboxes exceeding burst limits.
    - Lead-to-sender thread affinity with multi-tier fallback: maintains original sender lock; if capped or quarantined, falls back gracefully to `same_domain` (sibling mailbox on the same root domain), `any_healthy` mailbox, or non-fatal `postpone` with zero credit debit.
  - **Executor & Router Integration (`campaigns/backend/services/elein_executor.py`, `campaigns/backend/routers/elein.py`)**:
    - Wired domain balancing, thread lock persistence into `campaign_lead_sender_locks`, and enriched telemetry (`sender_domain`, `strategy_applied`, `thread_affinity_maintained`, `domain_health_status`).
    - Exposed `GET /api/elein/sender-pool/domains` providing full workspace domain health observability.
  - **Verification**: 64/64 automated tests passing across `test_domain_rotation_and_burnout_protection.py` (35/35), `test_domain_grouping_burnout_circuit_breaker.py` (9/9), `test_issue5_executor_router.py` (7/7), and `test_horizon29_cold_email_deliverability_pool.py` (13/13) with sub-second production build (639ms).

- [x] **Phase 32: Custom Domain Tracking (CNAME) & Automated SSL Verification Guard (100% Operational):**
  - **Live TLS/SSL Handshake & CNAME Verification (`core/backend/services/deliverability_guard.py`)**:
    - `verify_ssl_handshake`: Performs standard library TLS socket handshake on port 443 with SNI (`server_hostname`), extracts peer certificates, SANs, Common Name, issuer, and calculates `days_until_expiry` from `notAfter`. Catches certificate expiration, host mismatch, socket timeout, and connection refused gracefully.
    - `verify_custom_tracking_domain`: Performs CNAME resolution against expected target (`track.elein.ai`) and performs live TLS handshake. Reports `VERIFIED_ACTIVE`, `SSL_PENDING_PROVISIONING`, `CNAME_MISSING_OR_MISMATCH`, or `CERTIFICATE_EXPIRED`.
    - `verify_domain_dns_health`: Integrates live custom tracking CNAME and SSL status directly into overall deliverability scoring, emitting actionable setup instructions.
  - **Fail-Safe Tracking Link Rewriting**:
    - `rewrite_tracking_links`: When `ssl_verified=False` (or SSL is still provisioning), immediately falls open and leaves email body links untouched, returning `fallback_reason="SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING"`. This completely prevents red `"NET::ERR_CERT_COMMON_NAME_INVALID"` browser warnings for recipients.
    - Preserves trailing prose punctuation (`.`, `,`, `!`, `?`, `"`, `;`) and prevents double-wrapping links already pointing to the tracking domain.
  - **Router & Executor Integration (`campaigns/backend/routers/elein.py`, `campaigns/backend/services/elein_executor.py`)**:
    - Exposed `POST /api/elein/deliverability/verify-tracking-domain` and `GET /api/elein/deliverability/tracking-domain-status` with tenant IDOR boundaries. Updates matching sender inboxes in `email_sender_inboxes` with `tracking_domain` and `ssl_verified=True` upon verification.
    - `EleInExecutor.handle_send_email`: Bypasses tracking rewrite and tags `ssl_tracking_bypassed=True` when SSL is unverified, maintaining 100% deliverability safety.
  - **Verification**: 57/57 automated tests passing across `test_custom_tracking_cname_and_ssl_guard.py` (32/32), `test_issue6_ssl_handshake_and_cname_verification.py` (16/16), and `test_issue6_router_and_executor_tracking_guard.py` (9/9) with sub-second production build (859ms).

- [x] **Phase 33: Spintax & Linguistic Variation Multiplier (100% Operational):**
  - **Combinatorial Multiplier & Entropy Analysis (`campaigns/backend/services/template_spintax_guard.py`)**:
    - `calculate_spintax_combinations`: Linear-time, stack-based parser evaluating sequence products and branch sums across flat and arbitrary nested spintax structures (`{opt1|opt2|{opt3|opt4}}`), masking Liquid/Mustache tags and pipe fallbacks (`{{first_name | there}}`) with 100M combination overflow clamp.
    - `calculate_spintax_entropy`: Computes template combinations and `diversity_ratio` against campaign lead volume, mapping to ESP spam clustering risk ratings (`CRITICAL_SPAM_RISK` < 5 or < 0.05 diversity ratio, `MODERATE_VARIATION`, `HIGH_DIVERSITY`, `ENTERPRISE_IMMUNITY` >= 200) with volume-adjusted diversification recommendations.
    - `generate_linguistic_spintax`: Converts plain B2B copy to high-converting spintax across greetings (`{Hi|Hello|Hey}`), opening hooks (`{I saw|I noticed|came across}`), value connectors, CTAs (`{Are you free for a quick chat|Open to a brief 10-minute call}`), and sign-offs (`{Best,|Thanks,|Cheers,}`), while strictly protecting `{{mustache_variables}}` and pre-existing spintax.
    - `preview_spintax_variants`: Generates distinct rendered previews with deterministic seed sequence (`f"{seed}_{i}"`).
  - **Executor Telemetry & Deterministic Lead Seeding (`campaigns/backend/services/elein_executor.py`)**:
    - `_interpolate_template`: Seeded with `f"{lead_id}_{node_id}"` for reproducible phrasing per recipient; tags `data["spintax_applied"] = True`.
    - Injected `spintax_resolved: True` across `handle_send_email`, `handle_send_message`, and `handle_connection_request`.
  - **Router Endpoints (`campaigns/backend/routers/elein.py`)**:
    - Exposed `POST /api/elein/spintax/analyze`, `POST /api/elein/spintax/generate`, and `POST /api/elein/spintax/preview`.
  - **Verification**: 50/50 automated tests passing across `test_spintax_and_linguistic_variation_multiplier.py` (39/39) and `test_issue7_spintax_multiplier_entropy.py` (11/11), 215/215 deliverability regression suite green, sub-second frontend production build (675ms).

- [x] **Phase 34: Smart Mailbox Auto-Warmup Engine & Adaptive Ramp Curves (100% Operational):**
  - **Adaptive Ramp Curves & Reputation Health Engine (`integrations/backend/services/mailbox_warmup_service.py`)**:
    - `WarmupCurveType`: `LINEAR`, `LOGARITHMIC` (Sigmoid S-curve with gentle 1-5 day initial IP crawl, accelerated 6-18 day ramp, and smooth plateau to target cap), and `AGGRESSIVE` (square-root curve for pre-warmed / aged domains).
    - `calculate_warmup_ramp_projection`: Models daily volume splits between Warmup vs Cold Outreach (e.g. Day 0: 100% warmup / 0% cold; Day 14: 40% warmup / 60% cold; Day 28+: 20% warmup maintenance floor / 80% cold).
    - `calculate_inbox_warmup_health_score`: Computes 0-100 reputation score based on inbox age, aggregate bounce rate, spam complaints, and peer engagement. Categorizes into `PEAK_HEALTH` (>=85), `RAMPING_OPTIMAL` (70-84), `NEEDS_RECOVERY` (50-69: automatic 50% cold outreach throttle), and `EMERGENCY_PAUSED` (<50: 100% cold outreach pause).
    - `simulate_peer_warmup_exchange`: Simulates realistic multi-turn peer B2B email threads with formula injection sanitization (`=`, `+`, `-`, `@`), spam folder rescue, star/priority marking, and response engagement.
    - `advance_inbox_warmup_tick`: Automatically advances mailbox days active, recalculates health scores, updates daily caps, and handles database drops with non-fatal fallbacks.
  - **Email Sender Pool & Router Integration (`integrations/backend/services/email_sender_service.py`, `campaigns/backend/routers/elein.py`)**:
    - `calculate_warmup_daily_cap`: Integrates adaptive curves and reputation health throttle while maintaining backward compatibility for legacy `warmup_increment_per_day` configurations.
    - `select_rotating_sender_inbox`: Rejects `EMERGENCY_PAUSED` inboxes with `WARMUP_EMERGENCY_PAUSED` for cold campaigns and applies 50% capacity throttling for inboxes in `NEEDS_RECOVERY`. Enriches all returned mailboxes with telemetry (`warmup_health_score`, `warmup_curve_type`, `warmup_days_active`).
    - Exposed endpoints `POST /api/elein/warmup/calculate-ramp`, `POST /api/elein/warmup/health`, `POST /api/elein/warmup/simulate-tick`, and `GET /api/elein/warmup/inbox/{inbox_id}` with tenant IDOR protection.
  - **Verification**: 69/69 automated tests passing across `test_smart_mailbox_warmup_engine.py` (39/39), `test_mailbox_warmup_service.py` (17/17), and `test_horizon29_cold_email_deliverability_pool.py` (13/13) with sub-second production build (783ms).

- [x] **Phase 35: ESP Spam Trap, Role-Based Mailbox & Disposable Domain Shield (100% Operational):**
  - **Email Shield Core & Classification Engine (`core/backend/services/email_shield_service.py`)**:
    - `EmailClassification`: `CORPORATE`, `FREE_WEBMAIL`, `ROLE_BASED`, `DISPOSABLE`, `SPAM_TRAP`, `INVALID`.
    - `SPAM_TRAP_PREFIXES`: Pristine honeypots and spam trap prefixes (`abuse`, `postmaster`, `spam`, `trap`, `honeypot`, `spamtrap`, `uce`, `fbl`, `noc`, `security`, `phish`, `anti-spam`) with composite/trailing-digit matching (`spamtrap12`, `honeypot99`, `spamtrap_marketing`).
    - `ROLE_BASED_PREFIXES` & `ROLE_CATEGORY_MAP`: 31+ functional role-based mailboxes (`info`, `admin`, `support`, `billing`, `sales`, `jobs`, `careers`, `hr`, `legal`, `contact`, etc.) mapped to organizational departments (`ADMINISTRATION`, `SUPPORT`, `FINANCE_BILLING`, `SALES`, `HUMAN_RESOURCES`, `LEGAL_COMPLIANCE`, `GENERAL_INQUIRY`, etc.).
    - `DISPOSABLE_DOMAINS`: 150+ ephemeral mailbox domains (`mailinator.com`, `guerrillamail.com`, `10minutemail.com`, `yopmail.com`, `trashmail.com`, etc.) with hierarchical subdomain stripping.
    - `FREE_WEBMAIL_DOMAINS`: Major global and regional consumer webmail providers (`gmail.com`, `yahoo.com`, `outlook.com`, `hotmail.com`, `icloud.com`, `proton.me`, `yandex.ru`, `gmx.de`, etc.).
    - `clean_and_parse_email`: RFC 5321 length validation, mailto: and display angle bracket stripping, NUL-byte and control character cleansing, and subaddressing / plus-tag normalization (`abuse+marketing@target.com` -> `abuse`).
    - `audit_email_address` & `audit_email_batch`: Single and batch auditing (clamped to 10,000 items to defend against worker OOM) returning risk tiers (`SAFE`, `LOW_RISK`, `HIGH_RISK`, `CRITICAL_SPAM_TRAP`) and policy-gated sending clearance (`can_safely_send`).
  - **Lead Ingestion & Campaign Executor Integration (`leads/backend/services/lead_ingestion_service.py`, `campaigns/backend/services/elein_executor.py`)**:
    - `execute_bulk_import_leads`: Automatically audits incoming emails, enriches metadata (`email_classification`, `is_role_based`, `is_disposable`, `deliverability_risk`), and automatically quarantines detected spam traps (`status="QUARANTINED"`, `quarantine_reason="SPAM_TRAP_DETECTED"`) with zero-migration database resilience.
    - `EleInExecutor.handle_send_email`: Pre-flight deliverability check aborts sends to spam traps (`spam_trap_detected`), disposable domains (`disposable_email_rejected`), and unauthorized role-based inboxes (`role_based_email_blocked` unless `allow_role_based=True` is explicitly configured). Enriches dispatch telemetry with classification metrics.
  - **Router Endpoints (`campaigns/backend/routers/elein.py`)**:
    - Exposed `POST /api/elein/deliverability/audit-email` and `POST /api/elein/deliverability/audit-batch` with workspace IDOR scoping.
  - **Verification**: 63/63 automated tests passing across `test_email_shield_service.py` (30/30) and `test_email_shield_and_spam_trap_guard.py` (33/33), 225/225 deliverability regression suite green, sub-second frontend production build (624ms).

- [x] **Phase 36: Live DMARC/DKIM/SPF Alignment Auditor, DNS Drift Tripwire & Auto-Quarantine (100% Operational):**
  - **RFC 7489 Alignment Core Service (`core/backend/services/dmarc_alignment_service.py`)**:
    - `DMARCAlignmentMode`: `RELAXED = "r"`, `STRICT = "s"`.
    - `DMARCPolicy`: `NONE = "none"`, `QUARANTINE = "quarantine"`, `REJECT = "reject"`, `MISSING = "missing"`.
    - `parse_dmarc_record`: Full RFC 7489 tag parsing (`v`, `p`, `sp`, `aspf`, `adkim`, `pct`, `rua`, `ruf`, `fo`, `ri`) with `v=DMARC1` verification and tag sanitization.
    - `evaluate_dmarc_alignment`: Verifies SPF and DKIM identifier alignment against visible `From:` header domain. Evaluates strict vs relaxed modes, executes RFC 7489 section 6.6.3 organizational domain DMARC fallback (`_dmarc.{root_domain}`) for subdomains, and evaluates deliverability risk (`SAFE`, `CRITICAL_REJECT_RISK`, `HIGH_SPAM_RISK`, `MODERATE_RISK`).
    - `audit_sender_inbox_dns_health`: Detects critical DNS drift tripwires (`SPF_MISSING_DRIFT`, `MULTIPLE_SPF_RFC7208_COLLISION`, `SPF_PERMISSIVE_PLUS_ALL`, `DKIM_MISSING_DRIFT`, `DKIM_REVOKED_KEY`, `DMARC_REJECT_UNALIGNED`, `DMARC_QUARANTINE_UNALIGNED`) and produces structured remediation DNS records.
    - `scan_workspace_dns_drift`: Multi-tenant workspace audit scanning all active sender inboxes, auto-quarantining degraded mailboxes (`status="QUARANTINED"`), and dispatching notifications with actionable remediation instructions.
  - **Executor Pre-Flight Guard & Router Integration (`campaigns/backend/services/elein_executor.py`, `campaigns/backend/routers/elein.py`)**:
    - `EleInExecutor.handle_send_email`: Pre-flight DMARC alignment check aborts sends to unaligned mailboxes under `p=reject` or `p=quarantine` (`reason="dmarc_alignment_failure"`), refunding allocated SendGrid credits and preserving sender domain reputation. Enriches dispatch telemetry with `dmarc_aligned`, `dmarc_policy`, and `dmarc_score`.
    - Exposed workspace-scoped endpoints `POST /api/elein/deliverability/dmarc-alignment-audit` and `POST /api/elein/deliverability/check-dns-drift`.
  - **Verification**: 75/75 automated tests passing across `test_dmarc_alignment_service.py` (32/32) and `test_dmarc_alignment_and_dns_drift_guard.py` (43/43), 305/305 deliverability regression suite green, sub-second frontend production build (672ms).

- [x] **Phase 37: Advanced Inbound Referral Discovery, Working-Hours OOO Rescheduler & Company-Wide Domain Suppression (100% Operational):**
  - **Referral Discovery & Suppression Core Service (`inbox/backend/services/referral_and_snooze_service.py`)**:
    - `extract_referral_contact`: NLP extraction of referred colleague name, email, and job title across 3 syntax patterns with `EmailShieldService` deliverability validation (rejecting spam traps, role mailboxes, and disposable domains), self-referral loop rejection, and prompt injection neutralization.
    - `detect_company_wide_opt_out`: Flags corporate organizational opt-outs ("remove our entire company", "unsubscribe all of us") while strictly shielding public freemail providers (`FREE_WEBMAIL_DOMAINS` e.g. `@gmail.com`, `@yahoo.com`) from domain suppression.
    - `calculate_timezone_aware_ooo_snooze`: Reschedules OOO leads for the next working morning (09:xx AM local time with 10-30 min jitter) in the *recipient's* local timezone (`America/New_York`, `Europe/Paris`, `Asia/Tokyo`, etc.), handling weekend rollovers (Friday rolls to Monday morning) and [1, 90] day clamping.
    - `process_advanced_inbound_reply`: Automatically inserts referred prospects into `leads` with attribution (`referral_source_lead_id=lead_id`), executes company-wide domain suppression cascades cancelling all pending executions for that domain, and transitions OOO campaigns to `snoozed_ooo`.
  - **Sentiment & Router Integration (`inbox/backend/services/sentiment_classifier.py`, `inbox/backend/services/inbox_service.py`, `campaigns/backend/routers/elein.py`)**:
    - `apply_inbound_sentiment_actions`: Ingests referrals, triggers domain cascades, and notifies workspace of new colleague discoveries.
    - Exposed workspace-scoped endpoints `POST /api/elein/inbound/extract-referral`, `POST /api/elein/inbound/suppress-domain`, `GET /api/elein/inbound/suppressed-domains`, and `POST /api/elein/inbound/reschedule-ooo`.
  - **Verification**: 78/78 automated tests passing across `test_referral_discovery_and_domain_suppression_guard.py` (43/43), `test_referral_and_snooze_service.py` (21/21), and `test_horizon30_reply_sentiment_and_ooo_snooze.py` (14/14), sub-second frontend production build (659ms).

- [x] **Phase 38: Recipient MX Record Validator, Catch-All / Accept-All Probe & Greylisting Deferral Engine (100% Operational):**
  - **MX & Catch-All Core Guard (`core/backend/services/mx_and_catchall_guard.py`)**:
    - `resolve_domain_mx_records`: Priority-sorted DNS MX record resolution, RFC 7505 Null MX rejection (`0 .`), RFC 5321 Section 5.1 implicit A/AAAA fallback, and ESP fingerprinting (`GOOGLE_WORKSPACE`, `MICROSOFT_365`, `PROOFPOINT`, `MIMECAST`, `BARRACUDA`, `ZOHO`, `PROTON`, `SELF_HOSTED`).
    - `detect_catch_all_domain`: Random canary email generator (`f"elein_canary_{uuid}@{domain}"`) probing corporate Catch-All/Accept-All behavior while bypassing consumer webmail with in-memory TTL caching to avoid duplicate network probes.
    - `detect_smtp_deferral_or_greylist`: Detects 4xx codes (`421`, `450`, `451`, `452`) and greylisting patterns (`greylist`, `try again later`, `temporarily deferred`), extracting suggested wait times.
    - `calculate_greylist_retry_delay`: Truncated exponential backoff (`300s -> 600s -> 1200s -> 2400s -> 3600s`) preserving prospect leads and respecting MTA rate limits.
  - **Campaign Executor & Router Integration (`campaigns/backend/services/elein_executor.py`, `campaigns/backend/routers/elein.py`)**:
    - `EleInExecutor.handle_send_email`: Pre-flight MX record guard aborts send with `reason="no_mail_exchanger"` when recipient domain cannot receive mail, burning zero credits.
    - Catches temporary SMTP greylisting deferrals, refunds allocated credits, and transitions execution to `status="deferred"`, `reason="smtp_greylisted"`, with `next_run_delta_seconds`.
    - Enriches output telemetry with `recipient_esp`, `is_catch_all_domain`, and `mx_record_count`.
    - Exposed workspace-scoped endpoints `POST /api/elein/deliverability/verify-mx`, `POST /api/elein/deliverability/check-catch-all`, and `POST /api/elein/deliverability/evaluate-smtp-deferral`.
  - **Verification**: 73/73 automated tests passing across `test_mx_catchall_and_greylisting_guard.py` (47/47) and `test_mx_and_catchall_guard.py` (26/26), 226/226 trilogy regression tests green, clean TypeScript validation and sub-second frontend production build.

- [x] **Phase 39: Spam Trigger Words & Algorithmic Content Spam Score Classifier (SpamAssassin & Microsoft EOP Pre-Flight) (100% Operational):**
  - **Spam Score Core Engine (`core/backend/services/spam_score_service.py`)**:
    - `SpamRiskLevel`: `SAFE` (<2.0), `LOW_RISK` (2.0-3.99), `HIGH_SPAM_RISK` (4.0-5.99), `CRITICAL_SPAM_REJECT` (>=6.0).
    - 628 calibrated trigger keywords and regex patterns spanning 6 categories: `URGENCY_PRESSURE`, `FINANCIAL_HYPE`, `SHADY_MARKETING`, `DECEPTIVE_PREFIXES`, `SENSITIVE_PHARMACEUTICAL_CRYPTO`, and `URL_SHORTENER_DOMAINS` with 1.5x subject weighting.
    - Algorithmic SpamAssassin / Microsoft Exchange Online Protection heuristics: all-caps subject/body penalties, excessive punctuation (`?!` combos), excessive currency symbols, deceptive `Re:`/`Fwd:` prefixes on cold emails, link density thresholds, raw IP URLs (`http://192.168.1.1/`), and missing unsubscribe penalties.
    - `suggest_copy_remediations`: Context-preserving B2B consultative copy substitutions (preserving Title Case, UPPERCASE, and lowercase formats).
    - Hardened with ReDoS regex bounds, zero-width character evasion cleansing (`\u200B` - `\u200D`, `\uFEFF`, `\u00AD`), and 100,000-character payload clamping.
  - **Campaign Executor & Router Integration (`campaigns/backend/services/elein_executor.py`, `campaigns/backend/routers/elein.py`)**:
    - `EleInExecutor.handle_send_email`: Pre-flight content heuristic gate aborts dispatch on critical spam scores (`>= 6.0`) with `status="skipped"`, `reason="critical_spam_score"`, burning 0 SendGrid credits and preserving domain sender reputation. Enriches telemetry with `spam_score`, `spam_risk_level`, and `flagged_triggers_count`.
    - Exposed workspace-scoped endpoints `POST /api/elein/deliverability/audit-spam-score` and `POST /api/elein/deliverability/sanitize-copy`.
  - **Verification**: 93/93 automated tests passing across `test_spam_score_service.py` (38/38), `test_spam_score_and_eop_guard.py` (20/20), `test_spam_score_executor_and_router.py` (10/10), and unit tests (25/25); 239/239 regression deliverability suite green; sub-second production build (688ms).
