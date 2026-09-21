import { toast } from "sonner"
import { AlertCircle } from "lucide-react"
import { useLeadImport } from "../LeadImportContext"
import { CompanyAutocomplete } from "../../CompanyAutocomplete"
import { LocationAutocomplete } from "../../LocationAutocomplete"

export function SearchImport() {
  const { searchParams, setSearchParams, activeAccount, budget, liveUrl } = useLeadImport();

  const togglePill = (field: keyof typeof searchParams, val: string) => {
    const current = searchParams[field] as string[];
    if (current.includes(val)) {
      setSearchParams({ ...searchParams, [field]: current.filter(x => x !== val) });
    } else {
      setSearchParams({ ...searchParams, [field]: [...current, val] });
    }
  }

  return (
    <div className="space-y-8 animate-in fade-in pb-8">
      <div className="bg-primary/10 border border-primary/20 text-primary rounded-lg p-3 text-xs flex gap-2">
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <p>
          <strong>Pro Tip:</strong> For extreme precision (like exact city radiuses or specific industry codes), build your search directly on LinkedIn and paste the URL into the <strong>Sales Navigator</strong> tab instead!
        </p>
      </div>
      <div className="grid gap-2">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">General Keywords</label>
        <input value={searchParams.keywords} onChange={e => setSearchParams({...searchParams, keywords: e.target.value})} placeholder='e.g. "SaaS" OR "B2B"' className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      </div>
      <div className="space-y-3">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">JOB TITLE KEYWORDS</label>
        <div className="flex flex-wrap gap-2 mb-3">
          {["Founder", "CEO", "VP of Sales", "SDR", "BDR", "Account Executive", "Marketing Director", "Software Engineer"].map(t => (
            <button key={t} onClick={() => togglePill('jobTitles', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.jobTitles.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
          ))}
        </div>
        <input value={searchParams.customTitle} onChange={e => setSearchParams({...searchParams, customTitle: e.target.value})} placeholder='Or enter custom titles (comma separated)' className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="grid gap-2">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Location</label>
          <LocationAutocomplete 
            value={searchParams.location}
            onChange={val => setSearchParams({...searchParams, location: val})}
          />
        </div>
        <div className="grid gap-2">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">School / University</label>
          <input value={searchParams.school} onChange={e => setSearchParams({...searchParams, school: e.target.value})} placeholder='e.g. Stanford University' className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="grid gap-2">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Current Company</label>
          <CompanyAutocomplete 
            value={searchParams.company}
            onChange={val => setSearchParams({...searchParams, company: val})}
          />
        </div>
        <div className="grid gap-2">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Past Company</label>
          <input value={searchParams.pastCompany} onChange={e => setSearchParams({...searchParams, pastCompany: e.target.value})} placeholder='e.g. Google, Amazon' className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        </div>
      </div>
      <div className="space-y-3">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">INDUSTRY</label>
        <div className="flex flex-wrap gap-2">
          {["Software Development", "Financial Services", "Healthcare", "Marketing", "IT Services", "Real Estate", "Education", "Retail"].map(t => (
            <button key={t} onClick={() => togglePill('industries', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.industries.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">DEPARTMENT / FUNCTION</label>
        <div className="flex flex-wrap gap-2">
          {["Engineering", "Sales", "Marketing", "Operations", "HR", "Finance", "Legal"].map(t => (
            <button key={t} onClick={() => togglePill('department', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.department.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-3">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">CONNECTION</label>
          <div className="flex flex-wrap gap-2">
            {["1st degree", "2nd degree", "3rd+ degree"].map(t => (
               <button key={t} onClick={() => togglePill('network', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.network.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">SENIORITY</label>
          <div className="flex flex-wrap gap-2">
            {["Entry", "Senior", "Director", "VP", "CXO", "Partner", "Owner"].map(t => (
               <button key={t} onClick={() => togglePill('seniority', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.seniority.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="space-y-3">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">COMPANY HEADCOUNT</label>
        <div className="flex flex-wrap gap-2">
          {["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5000+"].map(t => (
             <button key={t} onClick={() => togglePill('companySize', t)} className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${searchParams.companySize.includes(t) ? 'bg-primary border-primary text-primary-foreground' : 'bg-transparent border-input text-foreground hover:bg-muted'}`}>{t}</button>
          ))}
        </div>
      </div>
      <div className="mt-10 p-5 rounded-xl border bg-muted/30">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-2">GENERATED LINKEDIN URL</label>
        <code className="block w-full p-4 rounded-lg bg-background border text-xs text-foreground font-mono overflow-x-auto break-all shadow-sm">
          {liveUrl || "Select filters above to instantly generate your URL..."}
        </code>
        <div className="flex gap-3 mt-4">
          <button onClick={() => { navigator.clipboard.writeText(liveUrl); toast.success("URL Copied to clipboard"); }} disabled={!liveUrl} className="px-5 py-2 rounded-md border border-input bg-background hover:bg-muted text-xs font-bold transition-colors disabled:opacity-50">Copy URL</button>
          <a href={liveUrl || "#"} target="_blank" rel="noreferrer" className={`px-5 py-2 rounded-md border border-input bg-background hover:bg-muted text-xs font-bold transition-colors flex items-center gap-2 ${!liveUrl ? 'opacity-50 pointer-events-none' : ''}`}>Open in LinkedIn ↗</a>
        </div>
      </div>

      {/* Daily Scrape Budget Meter */}
      <div className="mt-4 p-4 rounded-xl border bg-background">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Daily Scrape Budget</span>
          <span className="text-xs font-semibold text-foreground">{budget.used} / {budget.limit} used</span>
        </div>
        <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${budget.used / budget.limit > 0.85 ? 'bg-destructive' : budget.used / budget.limit > 0.6 ? 'bg-primary' : 'bg-success'}`}
            style={{ width: `${Math.min(100, (budget.used / budget.limit) * 100)}%` }}
          />
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">
          {activeAccount
            ? <><span className="inline-block w-2 h-2 rounded-full bg-success mr-1.5 animate-pulse" />Scraping via <span className="font-medium text-foreground">{activeAccount.name}</span> · {budget.remaining} profiles remaining today</>
            : <><span className="inline-block w-2 h-2 rounded-full bg-destructive mr-1.5" /><span className="text-destructive font-medium">No LinkedIn account connected.</span> Go to Accounts first.</>
          }
        </p>
      </div>
    </div>
  )
}
