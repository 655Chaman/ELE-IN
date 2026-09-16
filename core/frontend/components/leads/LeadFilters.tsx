import { Search, Filter, Link2, ChevronRight, Plus } from "lucide-react"

interface LeadFiltersProps {
  search: string
  setSearch: (val: string) => void
  listTypeFilter: string
  setListTypeFilter: (val: string) => void
  campaignFilter: string
  setCampaignFilter: (val: string) => void
  onAddLeads: () => void
}

export function LeadFilters({
  search,
  setSearch,
  listTypeFilter,
  setListTypeFilter,
  campaignFilter,
  setCampaignFilter,
  onAddLeads
}: LeadFiltersProps) {
  return (
    <div className="flex items-center gap-3 mb-6">
      <div className="flex items-center gap-2 flex-1 max-w-xs rounded-lg border border-border/50 bg-background/50 backdrop-blur-md px-3 py-2 shadow-sm">
        <Search size={13} className="text-muted-foreground shrink-0" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search lists…"
          className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground focus:outline-none"
        />
      </div>

      <div className="relative flex items-center">
        <Filter size={12} className="absolute left-3 text-muted-foreground pointer-events-none" />
        <select 
          value={listTypeFilter}
          onChange={(e) => setListTypeFilter(e.target.value)}
          className="appearance-none pl-8 pr-8 py-2 rounded-lg border border-border/50 bg-background/50 backdrop-blur-md text-xs text-muted-foreground hover:text-foreground transition-all shadow-sm focus:outline-none cursor-pointer"
        >
          <option value="all">List type: All</option>
          <option value="csv">CSV Uploads</option>
          <option value="sales_nav">Sales Navigator</option>
          <option value="search">Native Search</option>
          <option value="linkedin_url">Raw URLs</option>
        </select>
        <ChevronRight size={12} className="absolute right-3 text-muted-foreground pointer-events-none rotate-90 opacity-50" />
      </div>
      
      <div className="relative flex items-center">
        <Link2 size={12} className="absolute left-3 text-muted-foreground pointer-events-none" />
        <select 
          value={campaignFilter}
          onChange={(e) => setCampaignFilter(e.target.value)}
          className="appearance-none pl-8 pr-8 py-2 rounded-lg border border-border/50 bg-background/50 backdrop-blur-md text-xs text-muted-foreground hover:text-foreground transition-all shadow-sm focus:outline-none cursor-pointer"
        >
          <option value="all">All campaigns</option>
          <option value="assigned">Assigned to campaign</option>
          <option value="unassigned">Unassigned</option>
        </select>
        <ChevronRight size={12} className="absolute right-3 text-muted-foreground pointer-events-none rotate-90 opacity-50" />
      </div>

      <div className="flex-1" />

      <button 
        onClick={onAddLeads}
        className="flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-sm font-bold text-primary-foreground rounded-lg transition-all shadow-sm"
      >
        <Plus size={14} /> Add leads
      </button>
    </div>
  )
}
