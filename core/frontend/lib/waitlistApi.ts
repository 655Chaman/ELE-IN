/**
 * waitlistApi.ts
 * ==============
 * Three-Layer Paranoia Waitlist Client Transport.
 *
 * Layer 0: FastAPI Backend (/api/waitlist) when fullstack server is available.
 * Layer 1: Direct Supabase Serverless Bridge when hosted statically on GitHub Pages (no backend server needed).
 * Layer 2: Browser localStorage safety cache if Supabase migrations are pending, guaranteeing zero broken UI.
 */

import { supabase, isSupabaseConfigured } from "./supabase"

export interface WaitlistPayload {
  email: string
  full_name: string
  company?: string
  role?: string
  team_size?: string
  monthly_outbound_volume?: string
  primary_channel?: string
  referred_by_code?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  hp_website_security?: string
}

export interface WaitlistDiscount {
  code: string
  percent: number
  duration_months: number
  duration_label: string
  description: string
}

export interface WaitlistEntry {
  id?: string
  status?: string
  message?: string
  email: string
  full_name: string
  company?: string
  position: number
  referral_code: string
  referrals_count: number
  priority_score: number
  discount?: WaitlistDiscount
  is_new?: boolean
}

const QUEUE_BASELINE_OFFSET = 384
const DEFAULT_DISCOUNT: WaitlistDiscount = {
  code: "EARLY30",
  percent: 30,
  duration_months: 12,
  duration_label: "Entire 1st Year (12 Months)",
  description: "30% off all monthly and annual plans for your first 12 months.",
}

function generateLocalReferralCode(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  let suffix = ""
  for (let i = 0; i < 6; i++) {
    suffix += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return `ELE-${suffix}`
}

async function computeSupabasePosition(priorityScore: number, createdAt: string): Promise<number> {
  try {
    const { count: higherScoreCount } = await supabase
      .from("waitlist")
      .select("*", { count: "exact", head: true })
      .gt("priority_score", priorityScore)

    const { count: earlierSameScoreCount } = await supabase
      .from("waitlist")
      .select("*", { count: "exact", head: true })
      .eq("priority_score", priorityScore)
      .lt("created_at", createdAt)

    return Math.max(1, (higherScoreCount || 0) + (earlierSameScoreCount || 0) + 1 + QUEUE_BASELINE_OFFSET)
  } catch {
    return QUEUE_BASELINE_OFFSET + 1
  }
}

export async function submitWaitlistSignup(payload: WaitlistPayload): Promise<WaitlistEntry> {
  // Layer 2: Bot honeypot pass-through on client
  if (payload.hp_website_security && payload.hp_website_security.trim()) {
    return {
      status: "success",
      email: payload.email,
      full_name: payload.full_name,
      position: 420,
      referral_code: "ELE-B0TTRAP",
      referrals_count: 0,
      priority_score: 0,
      discount: DEFAULT_DISCOUNT,
      is_new: true,
    }
  }

  // Layer 0: Attempt FastAPI Backend first (works locally & on Render/Docker fullstack)
  try {
    const res = await fetch("/api/waitlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    const ct = res.headers.get("content-type") || ""
    if (res.ok && ct.includes("application/json")) {
      return await res.json()
    }
    // If backend returns 400 validation error, throw explicitly to notify user
    if (res.status === 400 && ct.includes("application/json")) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData?.detail || "Invalid waitlist input.")
    }
    // 404 / 502 / 503 means static hosting (e.g. GitHub Pages) without Python backend -> fall through to Layer 1!
  } catch (err: any) {
    if (err?.message && !err.message.includes("Failed to fetch") && !err.message.includes("NetworkError")) {
      // Re-throw explicit 400 validation errors
      if (err.message.includes("Invalid") || err.message.includes("required")) {
        throw err
      }
    }
  }

  // Layer 1: Direct Supabase Serverless Path (GitHub Pages production mode)
  const cleanEmail = payload.email.trim().toLowerCase()
  const cleanName = payload.full_name.trim()
  const cleanRefBy = payload.referred_by_code?.trim().toUpperCase() || null

  if (isSupabaseConfigured) {
    try {
    // 1. Check existing registration (Idempotent Amnesia Defense)
    const { data: existing, error: fetchErr } = await supabase
      .from("waitlist")
      .select("*")
      .eq("email", cleanEmail)
      .maybeSingle()

    if (!fetchErr && existing) {
      const pos = await computeSupabasePosition(existing.priority_score || 0, existing.created_at)
      return {
        status: "already_registered",
        message: "Welcome back! You are already on the priority waitlist.",
        id: existing.id,
        email: existing.email,
        full_name: existing.full_name,
        position: pos,
        referral_code: existing.referral_code,
        referrals_count: existing.referrals_count || 0,
        priority_score: existing.priority_score || 0,
        discount: DEFAULT_DISCOUNT,
        is_new: false,
      }
    }

    if (fetchErr && fetchErr.code !== "PGRST116") {
      throw fetchErr
    }

    // 2. Insert new waitlist entrant directly into Supabase
    const newRefCode = generateLocalReferralCode()
    const nowIso = new Date().toISOString()

    const { data: inserted, error: insertErr } = await supabase
      .from("waitlist")
      .insert({
        email: cleanEmail,
        full_name: cleanName,
        company: payload.company || null,
        role: payload.role || null,
        team_size: payload.team_size || null,
        monthly_outbound_volume: payload.monthly_outbound_volume || null,
        primary_channel: payload.primary_channel || null,
        referral_code: newRefCode,
        referred_by_code: cleanRefBy,
        status: "pending",
        discount_code: "EARLY30",
        discount_percent: 30,
        discount_duration: "first_year",
        utm_source: payload.utm_source || "website",
        utm_medium: payload.utm_medium || null,
        utm_campaign: payload.utm_campaign || null,
      })
      .select()
      .single()

    if (insertErr) {
      throw insertErr
    }

    // 3. Award referral boost via atomic RPC if referred
    if (cleanRefBy) {
      try {
        await supabase.rpc("increment_waitlist_referral", { p_ref_code: cleanRefBy })
      } catch {
        // Non-blocking if RPC isn't deployed yet
      }
    }

    const pos = await computeSupabasePosition(0, inserted?.created_at || nowIso)
    return {
      status: "success",
      message: "Welcome to the Ele-in waitlist! Your spot has been secured.",
      id: inserted?.id,
      email: cleanEmail,
      full_name: cleanName,
      position: pos,
      referral_code: inserted?.referral_code || newRefCode,
      referrals_count: 0,
      priority_score: 0,
      discount: DEFAULT_DISCOUNT,
      is_new: true,
    }
    } catch (sbErr) {
      console.warn("[Waitlist] Supabase serverless fallback engaged:", sbErr)
    }
  }

  // Layer 2: Emergency LocalStorage Cache (if Supabase migration has not been applied yet)
  try {
    const cacheKey = "elein_waitlist_fallback_cache"
    const raw = localStorage.getItem(cacheKey)
    const cache: Record<string, WaitlistEntry> = raw ? JSON.parse(raw) : {}
    if (cache[cleanEmail]) {
      return { ...cache[cleanEmail], is_new: false, status: "already_registered" }
    }
    const localEntry: WaitlistEntry = {
      status: "success",
      email: cleanEmail,
      full_name: cleanName,
      company: payload.company,
      position: QUEUE_BASELINE_OFFSET + Object.keys(cache).length + 1,
      referral_code: generateLocalReferralCode(),
      referrals_count: 0,
      priority_score: 0,
      discount: DEFAULT_DISCOUNT,
      is_new: true,
    }
    cache[cleanEmail] = localEntry
    localStorage.setItem(cacheKey, JSON.stringify(cache))
    return localEntry
  } catch {
    return {
      status: "success",
      email: cleanEmail,
      full_name: cleanName,
      position: QUEUE_BASELINE_OFFSET + 1,
      referral_code: generateLocalReferralCode(),
      referrals_count: 0,
      priority_score: 0,
      discount: DEFAULT_DISCOUNT,
      is_new: true,
    }
  }
}

export async function lookupWaitlistStatus(identifier: string): Promise<WaitlistEntry | null> {
  const cleanId = identifier.trim()
  if (!cleanId) return null

  // Layer 0: Backend API
  try {
    const res = await fetch(`/api/waitlist/status?q=${encodeURIComponent(cleanId)}`)
    const ct = res.headers.get("content-type") || ""
    if (res.ok && ct.includes("application/json")) {
      return await res.json()
    }
    if (res.status === 404 && ct.includes("application/json")) {
      return null // Truly not found in backend
    }
  } catch {
    // Fall through to Layer 1
  }

  // Layer 1: Direct Supabase query
  if (isSupabaseConfigured) {
    try {
      const isEmail = cleanId.includes("@")
      const query = isEmail
        ? supabase.from("waitlist").select("*").eq("email", cleanId.toLowerCase()).maybeSingle()
        : supabase.from("waitlist").select("*").eq("referral_code", cleanId.toUpperCase()).maybeSingle()

      const { data, error } = await query
      if (!error && data) {
        const pos = await computeSupabasePosition(data.priority_score || 0, data.created_at)
        return {
          id: data.id,
          email: data.email,
          full_name: data.full_name,
          company: data.company,
          position: pos,
          referral_code: data.referral_code,
          referrals_count: data.referrals_count || 0,
          priority_score: data.priority_score || 0,
          discount: DEFAULT_DISCOUNT,
        }
      }
    } catch {
      // Fall through to Layer 2
    }
  }

  // Layer 2: Check localStorage fallback cache
  try {
    const raw = localStorage.getItem("elein_waitlist_fallback_cache")
    if (raw) {
      const cache: Record<string, WaitlistEntry> = JSON.parse(raw)
      const lower = cleanId.toLowerCase()
      if (cache[lower]) return cache[lower]
      const byCode = Object.values(cache).find((e) => e.referral_code.toUpperCase() === cleanId.toUpperCase())
      if (byCode) return byCode
    }
  } catch {}

  return null
}

export async function fetchWaitlistStats(): Promise<number> {
  // Layer 0: Backend API
  try {
    const res = await fetch("/api/waitlist/stats")
    if (res.ok) {
      const ct = res.headers.get("content-type") || ""
      if (ct.includes("application/json")) {
        const data = await res.json()
        if (data?.total_waitlist_count) return data.total_waitlist_count
      }
    }
  } catch {}

  // Layer 1: Direct Supabase count
  if (isSupabaseConfigured) {
    try {
      const { count, error } = await supabase
        .from("waitlist")
        .select("*", { count: "exact", head: true })
      if (!error && typeof count === "number") {
        return count + QUEUE_BASELINE_OFFSET
      }
    } catch {}
  }

  return 1482
}
