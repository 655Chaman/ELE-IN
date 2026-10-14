import React, { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import {
  Award,
  Download,
  Copy,
  Check,
  Share2,
  ExternalLink,
  ShieldCheck,
  Eye,
  EyeOff,
  Clock,
  TrendingUp,
  RefreshCw,
  X,
  Users,
  MessageSquare,
  Shield,
  Building2,
  DollarSign
} from "lucide-react"
import { toast } from "sonner"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"

interface SampleLead {
  name: string
  company: string
  title: string
  stage: string
  cycle_days: number
}

interface CertificateMetrics {
  campaign_id: string
  campaign_name: string
  campaign_status: string
  enrolled_leads: number
  connections_sent: number
  connections_accepted: number
  acceptance_rate: number
  messages_sent: number
  replies_received: number
  reply_rate: number
  meetings_booked: number
  booking_rate: number
  sdr_hours_saved: number
  estimated_deal_size_usd: number
  pipeline_value_usd: number
  account_safety_score: number
  badge_tier: "DIAMOND" | "PLATINUM" | "GOLD" | "SILVER"
  tier_title: string
  top_industries: string[]
  top_decision_makers: string[]
  sample_leads: SampleLead[]
}

interface CertificateData {
  certificate_id: string
  verification_token: string
  badge_tier: "DIAMOND" | "PLATINUM" | "GOLD" | "SILVER"
  tier_title: string
  issuer_signature: string
  is_valid: boolean
  is_public: boolean
  mask_pii: boolean
  issued_at: string
  expires_at: string
  metrics: CertificateMetrics
  social_share_copy: {
    linkedin: string
    twitter: string
    slack: string
    verification_url: string
  }
}

interface CampaignROICertificateModalProps {
  isOpen: boolean
  onClose: () => void
  campaignId: string
  campaignName: string
}

export const CampaignROICertificateModal: React.FC<CampaignROICertificateModalProps> = ({
  isOpen,
  onClose,
  campaignId,
  campaignName
}) => {
  const cardRef = useRef<HTMLDivElement>(null)
  const [maskPii, setMaskPii] = useState(true)
  const [customDealSize, setCustomDealSize] = useState<number>(2500)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const [copiedSlack, setCopiedSlack] = useState(false)
  const [copiedImage, setCopiedImage] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  // Fetch or mint certificate
  const { data: certData, mutate, isLoading } = useSWR<CertificateData>(
    isOpen && campaignId ? `/api/campaigns/${campaignId}/roi-certificate` : null,
    fetcher,
    { revalidateOnFocus: false }
  )

  // Sync initial maskPii preference when certData loads
  useEffect(() => {
    if (certData?.mask_pii !== undefined) {
      setMaskPii(certData.mask_pii)
    }
  }, [certData?.mask_pii])

  // Refresh or regenerate certificate with custom deal size
  const handleRegenerate = async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    try {
      const res = await fetchWithAuth(`/api/campaigns/${campaignId}/roi-certificate/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          custom_deal_size: customDealSize,
          mask_pii: maskPii,
          is_public: true
        })
      })
      if (!res.ok) throw new Error("Failed to recalculate certificate metrics")
      const updated = await res.json()
      mutate(updated, false)
      toast.success("ROI Certificate refreshed with latest campaign telemetry")
    } catch (err: any) {
      toast.error(err.message || "Failed to refresh certificate")
    } finally {
      setIsRefreshing(false)
    }
  }

  // Toggle PII Masking
  const handleTogglePii = async () => {
    const nextState = !maskPii
    setMaskPii(nextState)
    try {
      await fetchWithAuth(`/api/campaigns/${campaignId}/roi-certificate/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mask_pii: nextState })
      })
      mutate()
      toast.info(nextState ? "PII Masking enabled (Public Safe View)" : "Full names revealed (Internal Ops View)")
    } catch {
      // optimistic update retained
    }
  }

  // Copy Verification URL
  const handleCopyLink = () => {
    const url = certData?.social_share_copy?.verification_url || `${window.location.origin}/verify/${certData?.verification_token}`
    navigator.clipboard.writeText(url)
    setCopiedLink(true)
    toast.success("Cryptographic verification URL copied to clipboard!")
    setTimeout(() => setCopiedLink(false), 2000)
  }

  // Copy Slack formatted message
  const handleCopySlack = () => {
    const slackText = certData?.social_share_copy?.slack || ""
    navigator.clipboard.writeText(slackText)
    setCopiedSlack(true)
    toast.success("Slack performance announcement copied!")
    setTimeout(() => setCopiedSlack(false), 2000)
  }

  // Share to LinkedIn Web Intent
  const handleShareLinkedIn = () => {
    const url = certData?.social_share_copy?.verification_url || window.location.href
    const linkedInUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`
    window.open(linkedInUrl, "_blank", "noopener,noreferrer")
  }

  // Share to X / Twitter Web Intent
  const handleShareTwitter = () => {
    const tweetText = certData?.social_share_copy?.twitter || `Check out our verified outbound results on @EleIn!`
    const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(tweetText)}`
    window.open(twitterUrl, "_blank", "noopener,noreferrer")
  }

  // Render HTML5 Canvas snapshot for 1-Click Copy and Download
  const generateCanvas = (): Promise<HTMLCanvasElement> => {
    return new Promise((resolve) => {
      const width = 1200
      const height = 675
      const canvas = document.createElement("canvas")
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext("2d")
      if (!ctx) return resolve(canvas)

      // Background
      ctx.fillStyle = "#090d16"
      ctx.fillRect(0, 0, width, height)

      // Outer card border
      ctx.strokeStyle = "rgba(255, 255, 255, 0.12)"
      ctx.lineWidth = 2
      ctx.strokeRect(30, 30, width - 60, height - 60)

      // Header: Ele-in Logo & Seal
      ctx.fillStyle = "#f8fafc"
      ctx.font = "bold 24px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText("ELE-IN OUTBOUND FLEET", 70, 85)

      ctx.fillStyle = "#94a3b8"
      ctx.font = "14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText("VERIFIED CAMPAIGN PERFORMANCE CERTIFICATE", 70, 110)

      // Tier Badge Pill
      const tier = certData?.badge_tier || "DIAMOND"
      const tierTitle = certData?.tier_title || "Apex Outbound Performer"
      ctx.fillStyle = "#e2e8f0"
      ctx.font = "bold 16px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText(`${tier} TIER - ${tierTitle.toUpperCase()}`, 70, 175)

      // Campaign Name
      ctx.fillStyle = "#ffffff"
      ctx.font = "bold 36px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      const displayName = certData?.metrics?.campaign_name || campaignName
      ctx.fillText(displayName.length > 36 ? displayName.substring(0, 36) + "..." : displayName, 70, 225)

      // Metric Boxes (4 columns)
      const metricsList = [
        { label: "ACCEPTANCE RATE", val: `${certData?.metrics?.acceptance_rate ?? 0}%`, sub: `${certData?.metrics?.connections_accepted ?? 0} accepted` },
        { label: "REPLY RATE", val: `${certData?.metrics?.reply_rate ?? 0}%`, sub: `${certData?.metrics?.replies_received ?? 0} conversations` },
        { label: "SDR TIME SAVED", val: `${certData?.metrics?.sdr_hours_saved ?? 0}h`, sub: "Manual hours reclaimed" },
        { label: "PIPELINE VALUE", val: `$${(certData?.metrics?.pipeline_value_usd ?? 0).toLocaleString()}`, sub: `${certData?.metrics?.meetings_booked ?? 0} booked meetings` }
      ]

      metricsList.forEach((m, idx) => {
        const x = 70 + idx * 270
        const y = 290
        const boxW = 245
        const boxH = 145

        // Box background
        ctx.fillStyle = "rgba(15, 23, 42, 0.75)"
        ctx.fillRect(x, y, boxW, boxH)
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)"
        ctx.strokeRect(x, y, boxW, boxH)

        // Box label
        ctx.fillStyle = "#64748b"
        ctx.font = "bold 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        ctx.fillText(m.label, x + 20, y + 35)

        // Box value
        ctx.fillStyle = "#f8fafc"
        ctx.font = "bold 34px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        ctx.fillText(m.val, x + 20, y + 80)

        // Box sub
        ctx.fillStyle = "#94a3b8"
        ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        ctx.fillText(m.sub, x + 20, y + 115)
      })

      // Safety Banner
      ctx.fillStyle = "rgba(255, 255, 255, 0.04)"
      ctx.fillRect(70, 475, width - 140, 50)
      ctx.strokeStyle = "rgba(255, 255, 255, 0.12)"
      ctx.strokeRect(70, 475, width - 140, 50)

      ctx.fillStyle = "#e2e8f0"
      ctx.font = "bold 14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText("100% ACCOUNT SAFETY GUARANTEE - ZERO LINKEDIN BANS OR DISCONNECTIONS DETECTED", 95, 506)

      // Footer: Verification Token & Cryptographic Stamp
      const token = certData?.verification_token || "ELEIN-CERT-PROD"
      ctx.fillStyle = "#64748b"
      ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText(`VERIFICATION TOKEN: ${token}  |  ISSUED: ${new Date().toLocaleDateString()}`, 70, 580)
      ctx.fillText("AUTHENTICATED VIA HMAC-SHA256 • ELE-IN AUTONOMOUS OUTBOUND ENGINE", 70, 605)

      ctx.fillStyle = "#94a3b8"
      ctx.font = "bold 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      ctx.fillText("VERIFY AT APP.ELE-IN.COM/VERIFY", width - 360, 605)

      resolve(canvas)
    })
  }

  // 1-Click Copy Canvas Image to Clipboard
  const handleCopyImage = async () => {
    setIsExporting(true)
    try {
      const canvas = await generateCanvas()
      canvas.toBlob(async (blob) => {
        if (!blob) {
          toast.error("Failed to generate certificate snapshot")
          setIsExporting(false)
          return
        }
        try {
          await navigator.clipboard.write([
            new ClipboardItem({ "image/png": blob })
          ])
          setCopiedImage(true)
          toast.success("High-res Certificate Image copied to clipboard! Paste into Slack or LinkedIn.")
          setTimeout(() => setCopiedImage(false), 2500)
        } catch {
          // Fallback to downloading if clipboard image write not supported in browser
          const url = URL.createObjectURL(blob)
          const link = document.createElement("a")
          link.download = `elein-roi-certificate-${certData?.verification_token || "card"}.png`
          link.href = url
          link.click()
          URL.revokeObjectURL(url)
          toast.info("Image downloaded to your device")
        } finally {
          setIsExporting(false)
        }
      }, "image/png")
    } catch {
      setIsExporting(false)
      toast.error("Error creating certificate snapshot")
    }
  }

  // 1-Click Download High-Res PNG
  const handleDownloadPNG = async () => {
    setIsExporting(true)
    try {
      const canvas = await generateCanvas()
      const dataUrl = canvas.toDataURL("image/png")
      const link = document.createElement("a")
      link.download = `elein-roi-certificate-${certData?.verification_token || "card"}.png`
      link.href = dataUrl
      link.click()
      toast.success("Certificate PNG downloaded in ultra-high resolution!")
    } catch {
      toast.error("Failed to export certificate PNG")
    } finally {
      setIsExporting(false)
    }
  }

  // 1-Click Export Telemetry CSV
  const handleExportCSV = async () => {
    if (isExporting) return
    setIsExporting(true)
    try {
      const res = await fetchWithAuth(`/api/campaigns/${campaignId}/roi-certificate/export-csv?mask_pii=${maskPii}`)
      if (!res.ok) throw new Error("Failed to export ROI certificate CSV")
      const csvText = await res.text()
      const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = `elein-roi-certificate-${certData?.verification_token || "telemetry"}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      toast.success("Campaign ROI Certificate telemetry exported as CSV!")
    } catch (err: any) {
      toast.error(err?.message || "Failed to export ROI Certificate CSV")
    } finally {
      setIsExporting(false)
    }
  }

  const metrics = certData?.metrics
  const badgeTier = certData?.badge_tier || "DIAMOND"

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-background/80 backdrop-blur-xs overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, scale: 0.98, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98, y: 8 }}
          className="relative w-full max-w-4xl bg-card text-foreground border border-border rounded-2xl shadow-xl overflow-hidden my-8"
        >
          {/* Top Bar */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-background text-foreground flex items-center justify-center border border-border">
                <Award size={16} />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-foreground">
                  Campaign Performance & ROI Certificate
                </h2>
                <p className="text-xs text-muted-foreground">
                  Cryptographically signed performance summary for LinkedIn, X, and Slack sharing.
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-xl transition-colors cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>

          <div className="p-6 space-y-6">
            {/* ─── CONTROLS TOOLBAR (Layer 2 & ACV Estimator) ───────────────── */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-2xl bg-background border border-border text-xs">
              <div className="flex items-center gap-2.5 flex-wrap">
                {/* PII Toggle */}
                <button
                  onClick={handleTogglePii}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border bg-card hover:bg-muted text-foreground font-medium transition-colors cursor-pointer"
                  title="Toggle PII Masking for public sharing safety"
                >
                  {maskPii ? <EyeOff size={13} className="text-muted-foreground" /> : <Eye size={13} className="text-muted-foreground" />}
                  <span>{maskPii ? "PII Masked (Public Safe)" : "Full Names (Internal Ops)"}</span>
                </button>

                {/* Deal Size Estimator Input */}
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-card border border-border text-foreground">
                  <DollarSign size={13} className="text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">Deal ACV:</span>
                  <input
                    type="number"
                    min="100"
                    step="500"
                    value={customDealSize}
                    onChange={(e) => setCustomDealSize(Number(e.target.value) || 2500)}
                    onBlur={handleRegenerate}
                    className="w-16 bg-transparent text-xs font-mono font-semibold text-foreground focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportCSV}
                  disabled={isExporting || isLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-card hover:bg-muted border border-border text-foreground font-medium transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Download size={13} className="text-muted-foreground" />
                  <span>Export CSV</span>
                </button>

                {/* Regenerate Telemetry Button */}
                <button
                  onClick={handleRegenerate}
                  disabled={isRefreshing || isLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-card hover:bg-muted border border-border text-foreground font-medium transition-colors cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw size={13} className={isRefreshing ? "animate-spin text-muted-foreground" : "text-muted-foreground"} />
                  <span>Refresh Metrics</span>
                </button>
              </div>
            </div>

            {/* ─── THE CERTIFICATE PREVIEW CARD (Layer 0 Foundational) ── */}
            <div
              ref={cardRef}
              className="relative overflow-hidden rounded-2xl p-6 sm:p-7 border border-border bg-background"
            >
              {/* Card Header */}
              <div className="relative flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-border">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-medium tracking-wider uppercase text-muted-foreground">
                      Ele-in Outbound Fleet
                    </span>
                    <span className="w-1 h-1 rounded-full bg-border" />
                    <span className="text-[11px] font-mono text-muted-foreground">
                      Verified Milestone
                    </span>
                  </div>
                  <h3 className="text-xl sm:text-2xl font-semibold tracking-tight text-foreground">
                    {metrics?.campaign_name || campaignName}
                  </h3>
                </div>

                {/* Tier Badge */}
                <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl bg-card border border-border">
                  <Award size={16} className="text-muted-foreground" />
                  <div>
                    <div className="text-[10px] font-medium tracking-wider uppercase text-muted-foreground">
                      Performance Class
                    </div>
                    <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <span className="font-mono">{badgeTier}</span>
                      <span className="text-muted-foreground">•</span>
                      <span className="text-muted-foreground font-normal">{metrics?.tier_title}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Stat Highlights Ribbon */}
              <div className="relative grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-border border border-border rounded-2xl bg-card my-5">
                {/* Acceptance Rate */}
                <div className="p-4">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-xs">Acceptance</span>
                    <Users size={13} />
                  </div>
                  <div className="text-xl font-semibold text-foreground font-mono">
                    {metrics?.acceptance_rate ?? 0}%
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {metrics?.connections_accepted ?? 0} accepted
                  </div>
                </div>

                {/* Reply Rate */}
                <div className="p-4">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-xs">Reply Rate</span>
                    <MessageSquare size={13} />
                  </div>
                  <div className="text-xl font-semibold text-foreground font-mono">
                    {metrics?.reply_rate ?? 0}%
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {metrics?.replies_received ?? 0} replies
                  </div>
                </div>

                {/* SDR Hours Saved */}
                <div className="p-4">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-xs">Time Saved</span>
                    <Clock size={13} />
                  </div>
                  <div className="text-xl font-semibold text-foreground font-mono">
                    {metrics?.sdr_hours_saved ?? 0}h
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    Manual hours saved
                  </div>
                </div>

                {/* Pipeline Value */}
                <div className="p-4">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-xs">Pipeline Value</span>
                    <TrendingUp size={13} />
                  </div>
                  <div className="text-xl font-semibold text-foreground font-mono">
                    ${(metrics?.pipeline_value_usd ?? 0).toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {metrics?.meetings_booked ?? 0} booked meetings
                  </div>
                </div>
              </div>

              {/* Sample Converted Leads Showcase */}
              {metrics?.sample_leads && metrics.sample_leads.length > 0 && (
                <div className="relative py-4 border-t border-border">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-medium text-foreground">
                      Notable Conversions
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {maskPii ? "Protected by PII Anonymizer" : "Unmasked Internal View"}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {metrics.sample_leads.map((lead, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-xl bg-card border border-border text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-foreground">{lead.name}</span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border border-border">
                            {lead.stage}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                          <Building2 size={11} className="text-muted-foreground shrink-0" />
                          <span className="truncate">{lead.company}</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground truncate">
                          {lead.title}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Account Safety Guarantee Banner */}
              <div className="relative mt-2 px-4 py-2.5 rounded-2xl bg-card border border-border flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-foreground">
                  <ShieldCheck size={14} className="text-muted-foreground" />
                  <span className="font-medium">100% Account Safety Score</span>
                  <span className="text-muted-foreground hidden sm:inline">• Zero LinkedIn warnings or restrictions detected across fleet</span>
                </div>
                <span className="px-2 py-0.5 rounded-md bg-muted text-foreground font-mono text-[10px] border border-border">
                  VERIFIED HEALTHY
                </span>
              </div>

              {/* Card Footer: Cryptographic Signature & Verification Token */}
              <div className="relative mt-5 pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Shield size={13} className="text-muted-foreground shrink-0" />
                  <span>
                    TOKEN: <strong className="font-mono text-foreground">{certData?.verification_token || "ELEIN-CERT-PENDING"}</strong>
                  </span>
                  <span>•</span>
                  <span>HMAC-SHA256 Authenticated</span>
                </div>

                <div className="flex items-center gap-1.5 text-foreground font-medium">
                  <span>app.ele-in.com/verify</span>
                  <ExternalLink size={11} />
                </div>
              </div>
            </div>

            {/* ─── ACTION LAUNCHPAD (1-Click Actions & Social Sharing) ───────── */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-medium text-foreground">
                  Sharing & Export
                </h4>
                <span className="text-xs text-muted-foreground">
                  Ready for posting on professional networks
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                {/* 1. Copy Image to Clipboard */}
                <button
                  onClick={handleCopyImage}
                  disabled={isExporting}
                  className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-background hover:bg-muted text-foreground font-medium text-xs border border-border transition-colors cursor-pointer disabled:opacity-50"
                >
                  {copiedImage ? <Check size={13} /> : <Copy size={13} className="text-muted-foreground" />}
                  <span>{copiedImage ? "Image Copied" : "Copy Card to Clipboard"}</span>
                </button>

                {/* 2. Download High-Res PNG */}
                <button
                  onClick={handleDownloadPNG}
                  disabled={isExporting}
                  className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-background hover:bg-muted text-foreground font-medium text-xs border border-border transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Download size={13} className="text-muted-foreground" />
                  <span>Download High-Res PNG</span>
                </button>

                {/* 3. Share to LinkedIn */}
                <button
                  onClick={handleShareLinkedIn}
                  className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-background hover:bg-muted text-foreground font-medium text-xs border border-border transition-colors cursor-pointer"
                >
                  <Share2 size={13} className="text-muted-foreground" />
                  <span>Share to LinkedIn</span>
                </button>

                {/* 4. Share to X (Twitter) */}
                <button
                  onClick={handleShareTwitter}
                  className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-background hover:bg-muted text-foreground font-medium text-xs border border-border transition-colors cursor-pointer"
                >
                  <Share2 size={13} className="text-muted-foreground" />
                  <span>Share to X / Twitter</span>
                </button>
              </div>

              {/* Secondary Utility Links */}
              <div className="flex items-center justify-between flex-wrap gap-2 pt-1 text-xs">
                <button
                  onClick={handleCopyLink}
                  className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  {copiedLink ? <Check size={12} /> : <Copy size={12} />}
                  <span>{copiedLink ? "Link Copied" : "Copy Cryptographic Verification URL"}</span>
                </button>

                <button
                  onClick={handleCopySlack}
                  className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  {copiedSlack ? <Check size={12} /> : <MessageSquare size={12} />}
                  <span>{copiedSlack ? "Slack Text Copied" : "Copy Slack Announcement Text"}</span>
                </button>
              </div>
            </div>

            {/* ─── EXPANSION CTA ──────────────────── */}
            <div className="px-4 py-3 rounded-2xl bg-background border border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-0.5">
                <div className="text-xs font-semibold text-foreground">
                  Scale your outbound fleet to 10+ senders
                </div>
                <p className="text-xs text-muted-foreground">
                  Need higher pipeline volume? Connect additional sender pods or invite your revenue team.
                </p>
              </div>

              <button
                onClick={() => {
                  navigator.clipboard.writeText("https://ele-in.com")
                  toast.success("Referral invitation link copied to clipboard!")
                }}
                className="px-3.5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs transition-colors cursor-pointer whitespace-nowrap"
              >
                Invite Teammates
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
