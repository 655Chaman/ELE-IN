import { Search, Plus, X, Layers, CheckCircle2, FileSpreadsheet, Compass, Globe, Link2 } from "lucide-react"
import { cn } from "@/lib/utils"

export interface LeadTypeCounts {
  all?: number
  csv?: number
  sales_nav?: number
  search?: number
  linkedin_url?: number
}

export interface CampaignCounts {
  all?: number
  assigned?: number
  unassigned?: number
}

interface LeadFiltersProps {
  search: string
  setSearch: (val: string) => void
  listTypeFilter: string
  setListTypeFilter: (val: string) => void
  campaignFilter: string
  setCampaignFilter: (val: string) => void
  onAddLeads: () => void
  typeCounts?: LeadTypeCounts
  campaignCounts?: CampaignCounts
  totalFilteredLeads?: number
  totalFilteredLists?: number
}

const LIST_TYPE_TABS = [
  { id: "all", label: "All Lists", icon: Layers },
  { id: "csv", label: "CSV Uploads", icon: FileSpreadsheet },
  { id: "sales_nav", label: "Sales Navigator", icon: Compass },
  { id: "search", label: "Native Search", icon: Search },
  { id: "linkedin_url", label: "Raw URLs", icon: Globe },
]

const CAMPAIGN_TABS = [
  { id: "all", label: "All Statuses" },
  { id: "unassigned", label: "Unassigned" },
  { id: "assigned", label: "In Campaign" },
]

export function LeadFilters({
  search,
  setSearch,
  listTypeFilter,
  setListTypeFilter,
  campaignFilter,
  setCampaignFilter,
  onAddLeads,
  typeCounts,
  campaignCounts,
  totalFilteredLeads = 0,
  totalFilteredLists = 0,
}: LeadFiltersProps) {
  return (
    <div className="space-y-4 mb-6">
      {/* ─── Top Row: Search Bar & Primary CTA ─── */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md flex items-center rounded-xl border border-border/50 bg-background/60 backdrop-blur-md px-3.5 py-2.5 shadow-sm focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
          <Search size={14} className="text-muted-foreground shrink-0 mr-2.5" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search lists by name, type, or tags..."
            className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground/60 focus:outline-none"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="text-muted-foreground hover:text-foreground p-0.5 rounded-full hover:bg-muted/50 transition-colors"
              aria-label="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={onAddLeads}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-xs font-bold text-primary-foreground rounded-xl transition-colors shadow-xs shrink-0 cursor-pointer"
        >
          <Plus size={14} strokeWidth={2.5} /> Add leads
        </button>
      </div>

      {/* ─── Middle Row: Filter Chips with Responsive Layout & Clean Badges ─── */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pt-2 border-t border-border/40">
        {/* Source Type Chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          {LIST_TYPE_TABS.map((tab) => {
            const Icon = tab.icon
            const active = listTypeFilter === tab.id
            const count = typeCounts ? (typeCounts as any)[tab.id] : undefined

            return (
              <button
                key={tab.id}
                onClick={() => setListTypeFilter(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all border shrink-0 cursor-pointer",
                  active
                    ? "bg-foreground/10 border-foreground/20 text-foreground font-semibold shadow-xs"
                    : "bg-background/40 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/30"
                )}
              >
                <Icon size={12} className={cn(active ? "text-primary" : "text-muted-foreground/70")} />
                <span>{tab.label}</span>
                {count !== undefined && count > 0 && (
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.2 rounded-md font-bold ml-0.5",
                      active
                        ? "bg-primary/20 text-primary"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Campaign Assignment Status Chips */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className="h-3.5 w-px bg-border/60 mx-1 hidden sm:block" />
          {CAMPAIGN_TABS.map((tab) => {
            const active = campaignFilter === tab.id
            const count = campaignCounts ? (campaignCounts as any)[tab.id] : undefined

            return (
              <button
                key={tab.id}
                onClick={() => setCampaignFilter(tab.id)}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all border shrink-0 cursor-pointer",
                  active
                    ? "bg-primary/10 border-primary/30 text-primary font-semibold"
                    : "bg-background/30 border-border/30 text-muted-foreground hover:text-foreground hover:bg-muted/20"
                )}
              >
                {tab.id === "assigned" && <Link2 size={11} className="shrink-0" />}
                {tab.id === "unassigned" && <CheckCircle2 size={11} className="shrink-0" />}
                <span>{tab.label}</span>
                {count !== undefined && count > 0 && (
                  <span className="text-[10px] opacity-80 font-mono ml-0.5">({count})</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* ─── Bottom Yield Summary Bar ─── */}
      <div className="flex items-center justify-between text-xs text-muted-foreground px-0.5 pt-0.5">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-primary/70" />
          <span>
            Showing <strong className="text-foreground font-semibold">{totalFilteredLists}</strong> {totalFilteredLists === 1 ? "list" : "lists"}
            {totalFilteredLeads > 0 ? (
              <> containing <strong className="text-foreground font-semibold">{totalFilteredLeads.toLocaleString()}</strong> leads</>
            ) : null}
          </span>
        </div>
        {campaignFilter === "unassigned" && totalFilteredLeads > 0 && (
          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
            Ready to enroll into a campaign
          </span>
        )}
      </div>
    </div>
  )
}
