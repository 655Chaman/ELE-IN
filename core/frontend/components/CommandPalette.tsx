import { useState, useEffect, useRef, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "motion/react"
import {
  Search, Zap, UserPlus, Inbox, BookOpen, LayoutDashboard,
  Megaphone, Users, ShieldCheck, Settings, CreditCard, ArrowRight, CornerDownLeft
} from "lucide-react"
import { Linkedin } from "./icons/Linkedin"
import { ElesiumLogo } from "@/components/ElesiumLogo"

interface PaletteItem {
  id: string
  title: string
  subtitle: string
  category: "Actions" | "Navigation"
  icon: any
  path: string
  color: string
  bg: string
  badge?: string
  useElesiumLogo?: boolean
}

const PALETTE_ITEMS: PaletteItem[] = [
  // Quick Actions
  {
    id: "new_campaign",
    title: "Launch New Campaign",
    subtitle: "Build a multi-touch outreach sequence with Elesium Automation (elesium.online)",
    category: "Actions",
    icon: Zap,
    path: "/elein/campaigns/new",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-500/10",
    badge: "Create",
    useElesiumLogo: true
  },
  {
    id: "import_leads",
    title: "Import Lead List",
    subtitle: "Upload CSV, sync Sales Navigator, or paste LinkedIn URLs",
    category: "Actions",
    icon: UserPlus,
    path: "/elein/leads",
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-500/10",
    badge: "Import"
  },
  {
    id: "connect_account",
    title: "Connect LinkedIn Account",
    subtitle: "Add new sender profile with anti-ban warmup rotation",
    category: "Actions",
    icon: Linkedin,
    path: "/elein/accounts",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-500/10",
    badge: "Sender"
  },
  {
    id: "review_replies",
    title: "Review Elesium Reply Approvals",
    subtitle: "Inspect prospect responses and fine-tune Elesium-generated drafts (elesium.online)",
    category: "Actions",
    icon: Inbox,
    path: "/elein/inbox",
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-500/10",
    badge: "HITL",
    useElesiumLogo: true
  },
  {
    id: "brand_constitution",
    title: "Elesium AI Brand Constitution",
    subtitle: "Refine value propositions, buyer personas, and objection playbooks",
    category: "Actions",
    icon: BookOpen,
    path: "/elein/knowledge",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-500/10",
    badge: "Elesium",
    useElesiumLogo: true
  },
  {
    id: "elesium_portal",
    title: "Visit Elesium Automation",
    subtitle: "Enterprise AI & workflow automation studio (elesium.online)",
    category: "Actions",
    icon: Zap,
    path: "https://elesium.online",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-500/10",
    badge: "Official",
    useElesiumLogo: true
  },

  // Navigation
  {
    id: "nav_dashboard",
    title: "Dashboard Pulse",
    subtitle: "High-level analytics, active replies, and account radar",
    category: "Navigation",
    icon: LayoutDashboard,
    path: "/elein/dashboard",
    color: "text-foreground",
    bg: "bg-muted"
  },
  {
    id: "nav_campaigns",
    title: "Campaigns Hub",
    subtitle: "Manage, pause, and track all live campaigns",
    category: "Navigation",
    icon: Megaphone,
    path: "/elein/campaigns",
    color: "text-foreground",
    bg: "bg-muted"
  },
  {
    id: "nav_leads",
    title: "Leads Vault",
    subtitle: "Enrolled targets, verified emails, and list management",
    category: "Navigation",
    icon: Users,
    path: "/elein/leads",
    color: "text-foreground",
    bg: "bg-muted"
  },
  {
    id: "nav_accounts",
    title: "Senders & Warmup Radar",
    subtitle: "Daily quotas, proxy assignment, and session health",
    category: "Navigation",
    icon: ShieldCheck,
    path: "/elein/accounts",
    color: "text-foreground",
    bg: "bg-muted"
  },
  {
    id: "nav_settings",
    title: "Sending Safety & Settings",
    subtitle: "Account limits, team workspace members, and safety defaults",
    category: "Navigation",
    icon: Settings,
    path: "/elein/settings",
    color: "text-foreground",
    bg: "bg-muted"
  },
  {
    id: "nav_billing",
    title: "Billing & Workspace Credits",
    subtitle: "Credit balances, top-ups, invoices, and active package",
    category: "Navigation",
    icon: CreditCard,
    path: "/elein/billing",
    color: "text-foreground",
    bg: "bg-muted"
  }
]

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setIsOpen((open) => !open)
      }
      if (e.key === "Escape") {
        setIsOpen(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  useEffect(() => {
    if (isOpen) {
      setSearch("")
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen])

  const filteredItems = useMemo(() => {
    if (!search.trim()) return PALETTE_ITEMS
    const q = search.toLowerCase()
    return PALETTE_ITEMS.filter((item) =>
      item.title.toLowerCase().includes(q) ||
      item.subtitle.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q)
    )
  }, [search])

  useEffect(() => {
    setSelectedIndex(0)
  }, [search])

  const handleExecute = (path: string) => {
    setIsOpen(false)
    if (path.startsWith("http://") || path.startsWith("https://")) {
      window.open(path, "_blank", "noopener,noreferrer")
    } else {
      navigate(path)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    const handleNavigation = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((i) => (i + 1) % Math.max(filteredItems.length, 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((i) => (i - 1 + filteredItems.length) % Math.max(filteredItems.length, 1))
      } else if (e.key === "Enter" && filteredItems.length > 0) {
        e.preventDefault()
        handleExecute(filteredItems[selectedIndex].path)
      }
    }
    window.addEventListener("keydown", handleNavigation)
    return () => window.removeEventListener("keydown", handleNavigation)
  }, [isOpen, filteredItems, selectedIndex])

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[100]"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -16 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="fixed top-[15vh] left-1/2 -translate-x-1/2 w-full max-w-xl bg-card border border-border shadow-2xl rounded-2xl overflow-hidden z-[101]"
          >
            {/* Search Input Bar */}
            <div className="flex items-center px-4 py-3.5 border-b border-border bg-muted/20">
              <Search className="w-5 h-5 text-muted-foreground mr-3 shrink-0" />
              <input
                ref={inputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Type a command or jump to page…"
                role="combobox"
                aria-expanded={isOpen}
                aria-controls="command-listbox"
                aria-activedescendant={filteredItems[selectedIndex]?.id}
                className="flex-1 bg-transparent border-none text-base text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-0"
              />
              <div className="flex items-center gap-1.5 shrink-0">
                <kbd className="px-2 py-0.5 bg-muted border border-border rounded text-[11px] font-mono text-muted-foreground">esc</kbd>
              </div>
            </div>

            {/* Listbox */}
            <div id="command-listbox" role="listbox" className="max-h-[55vh] overflow-y-auto p-2">
              {filteredItems.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No commands matching "{search}".
                </div>
              ) : (
                filteredItems.map((item, index) => {
                  const Icon = item.icon
                  const isSelected = index === selectedIndex
                  const isFirstOfCategory = index === 0 || filteredItems[index - 1].category !== item.category

                  return (
                    <div key={item.id}>
                      {isFirstOfCategory && (
                        <div className="px-3 pt-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                          {item.category}
                        </div>
                      )}
                      <button
                        id={item.id}
                        role="option"
                        aria-selected={isSelected}
                        onClick={() => handleExecute(item.path)}
                        onMouseEnter={() => setSelectedIndex(index)}
                        className={`w-full flex items-center text-left px-3.5 py-2.5 rounded-xl transition-all cursor-pointer group ${
                          isSelected
                            ? "bg-primary/10 border border-primary/25 shadow-xs"
                            : "hover:bg-muted/50 border border-transparent"
                        }`}
                      >
                        <div className={`p-2 rounded-lg mr-3.5 shrink-0 ${item.bg}`}>
                          {item.useElesiumLogo ? (
                            <ElesiumLogo size={16} />
                          ) : (
                            <Icon className={`w-4 h-4 ${item.color}`} />
                          )}
                        </div>
                        <div className="flex-1 min-w-0 pr-2">
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-semibold truncate ${isSelected ? "text-primary" : "text-foreground"}`}>
                              {item.title}
                            </span>
                            {item.badge && (
                              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">
                                {item.badge}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground truncate mt-0.5">
                            {item.subtitle}
                          </div>
                        </div>
                        <div className="shrink-0">
                          {isSelected ? (
                            <CornerDownLeft size={14} className="text-primary" />
                          ) : (
                            <ArrowRight size={14} className="text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity" />
                          )}
                        </div>
                      </button>
                    </div>
                  )
                })
              )}
            </div>

            {/* Footer Navigation Hints */}
            <div className="px-4 py-2.5 border-t border-border bg-muted/20 flex items-center justify-between text-[11px] text-muted-foreground">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border text-[10px] font-mono">↑↓</kbd> Navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border text-[10px] font-mono">↵</kbd> Select
                </span>
              </div>
              <span className="font-semibold text-foreground/80">
                Ele-in Command Center
              </span>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
