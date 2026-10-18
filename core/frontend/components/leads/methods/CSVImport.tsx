import { useState } from "react"
import Papa from "papaparse"
import { motion } from "motion/react"
import { toast } from "sonner"
import { Download, LayoutTemplate, Sparkles, Upload, Rocket, ArrowRight, ShieldCheck, CheckCircle2, AlertTriangle, Table, Eye } from "lucide-react"
import { useLeadImport } from "../LeadImportContext"
import { usePaywall } from "@/contexts/PaywallContext"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { CustomSelect } from "@/components/ui/select"

export function CSVImport() {
  const { 
    step, 
    file, setFile, 
    cleanData, setCleanData, 
    headers, setHeaders, 
    sampleRows, setSampleRows,
    mappings, setMappings, 
    billing, 
    fileInputRef,
    detectedRowCount, setDetectedRowCount,
    name
  } = useLeadImport();

  const { openPaywall } = usePaywall();
  const isPro = billing?.tier === 'PRO' || billing?.tier === 'ENTERPRISE';
  const [isDragging, setIsDragging] = useState(false);

  const processSelectedFile = async (selected: File) => {
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      toast.error("Please select a .csv file. Excel spreadsheets (.xlsx) can be exported to CSV.");
      return;
    }
    // Paranoia Layer 1 & 2: Cap upload file size to prevent browser memory crashes / V8 lockups
    if (selected.size > 25 * 1024 * 1024) {
      toast.error("File size exceeds 25MB limit. Please upload a smaller CSV or split the file.");
      return;
    }
    setFile(selected);

    // Fast non-blocking row count calculation
    try {
      if (selected.size < 5 * 1024 * 1024) {
        const text = await selected.text();
        const lines = text.split(/\r\n|\n/).filter(line => line.trim().length > 0);
        setDetectedRowCount(Math.max(0, lines.length - 1));
      } else {
        const slice = selected.slice(0, 256 * 1024);
        const text = await slice.text();
        const sampleLines = text.split(/\r\n|\n/).filter(line => line.trim().length > 0);
        const avgBytesPerLine = (256 * 1024) / Math.max(1, sampleLines.length);
        setDetectedRowCount(Math.round(selected.size / avgBytesPerLine));
      }
    } catch (err) {
      setDetectedRowCount(0);
    }

    Papa.parse(selected, {
      header: true,
      preview: 5,
      complete: (results: any) => {
        if (results.meta.fields) {
          const fields: string[] = results.meta.fields;
          setHeaders(fields);
          if (results.data && Array.isArray(results.data)) {
            setSampleRows(results.data.slice(0, 5));
          }
          const guess = (keywords: string[]) => fields.find((f: string) => {
            const lower = f.toLowerCase().trim();
            return keywords.some((k: string) => lower === k || lower.includes(k));
          }) || "";
          const guessedFirst = guess(['first_name', 'first name', 'firstname', 'fname', 'first', 'given']);
          const guessedLast = guess(['last_name', 'last name', 'lastname', 'lname', 'last', 'surname']);
          const guessedFull = guess(['full_name', 'full name', 'fullname', 'contact name', 'lead name', 'prospect name', 'name']);
          const guessedLinkedin = guess(['linkedin_url', 'linkedin url', 'linkedin', 'profile_url', 'profile url', 'url', 'profile', 'sales navigator url', 'sales_nav_url']);
          const guessedEmail = guess(['email', 'e-mail', 'work email', 'work_email', 'email address', 'email_address', 'mail', 'contact email', 'lead email']);
          const guessedCompany = guess(['company_name', 'company name', 'company', 'organization', 'org', 'account', 'employer']);
          const guessedTitle = guess(['job_title', 'job title', 'title', 'position', 'role', 'designation', 'occupation', 'headline']);
          const guessedLocation = guess(['location', 'city', 'country', 'geo', 'state', 'region', 'address']);

          setMappings({
            first_name: guessedFirst,
            last_name: guessedLast,
            full_name: (!guessedFirst && guessedFull) ? guessedFull : "",
            linkedin_url: guessedLinkedin,
            email: guessedEmail,
            company_name: guessedCompany,
            job_title: guessedTitle,
            location: guessedLocation,
          });
        }
      }
    });
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      processSelectedFile(selected);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) {
      processSelectedFile(dropped);
    }
  };

  const hygieneCost = detectedRowCount > 0 ? Math.max(1, Math.ceil(detectedRowCount / 100)) : 1;

  return (
    <>
      {step === 1 && (
        <div className="animate-in fade-in max-w-xl space-y-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">Upload CSV File</label>
              <a href="/template_leads.csv" download className="text-xs text-primary hover:underline flex items-center gap-1"><Download size={12} /> Download template</a>
            </div>
            <div
              role="button"
              tabIndex={0}
              aria-label="Upload CSV file"
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-dashed border-2 rounded-lg p-10 flex flex-col items-center gap-3 transition-all cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                isDragging 
                  ? "border-primary bg-primary/10 scale-[1.01]" 
                  : "border-border hover:border-primary/70 hover:bg-primary/5 bg-muted/20"
              }`}
              onClick={() => fileInputRef.current?.click()}
            >
              <input type="file" ref={fileInputRef} className="hidden" accept=".csv" onChange={handleFileChange} />
              <div className="p-5 rounded-lg bg-background border border-border/60 shadow-xs"><Upload size={24} className="text-foreground" /></div>
              <div className="text-center">
                <p className="text-sm font-semibold">{file ? <span className="text-primary">{file.name}</span> : (isDragging ? "Drop your CSV file here" : "Click to browse or drag CSV here")}</p>
                <p className="text-xs font-medium text-muted-foreground mt-1">Max 25MB · CSV only</p>
                <p className="text-[10px] text-muted-foreground mt-1">Supports: First Name, Last Name, LinkedIn, Company</p>
              </div>
            </div>
          </div>

          {/* Lead Volume Pay Ramp: High-Intent Audience Priming */}
          {file && detectedRowCount > 50 && !isPro && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border border-primary/30 bg-gradient-to-br from-primary/10 via-background to-primary/5 p-5 shadow-xs relative overflow-hidden"
            >
              <div className="flex items-start justify-between gap-4 relative z-10">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-md bg-primary/20 text-primary flex items-center justify-center font-bold shrink-0">
                    <Rocket size={20} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-primary">Audience Detected</span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary text-primary-foreground">
                        {detectedRowCount.toLocaleString()} Leads
                      </span>
                    </div>
                    <h4 className="text-sm font-bold text-foreground mt-0.5">
                      Target ~{Math.max(1, Math.round(detectedRowCount * 0.035))} booked meetings from this list
                    </h4>
                  </div>
                </div>
              </div>

              {/* Free vs Growth Breakdown */}
              <div className="grid grid-cols-3 gap-2.5 my-4 relative z-10 text-center">
                <div className="bg-background/80 backdrop-blur-sm border border-border/50 rounded-lg p-2.5">
                  <span className="text-[10px] font-medium text-muted-foreground block">Free Tier</span>
                  <span className="text-xs font-bold text-muted-foreground">1 Campaign</span>
                </div>
                <div className="bg-background/80 backdrop-blur-sm border border-primary/30 rounded-lg p-2.5">
                  <span className="text-[10px] font-bold text-primary block">Growth Scale</span>
                  <span className="text-xs font-black text-foreground">20 Campaigns</span>
                </div>
                <div className="bg-background/80 backdrop-blur-sm border border-success/30 rounded-lg p-2.5">
                  <span className="text-[10px] font-bold text-success block">Monthly Fuel</span>
                  <span className="text-xs font-black text-foreground">5,000 Credits</span>
                </div>
              </div>

              {/* Primary Call to Action */}
              <div className="space-y-2 relative z-10">
                <button
                  type="button"
                  onClick={() => openPaywall({ 
                    campaignName: name || file?.name?.replace(/\.csv$/i, '') || "CSV Outreach",
                    featureName: `${detectedRowCount.toLocaleString()} Prospect Outreach`
                  })}
                  className="w-full py-3 px-4 rounded-lg bg-foreground text-background font-bold text-xs hover:opacity-90 active:opacity-95 transition-opacity flex items-center justify-center gap-2 shadow-xs group"
                >
                  <span>Unlock Growth Tier to Outreach All {detectedRowCount.toLocaleString()} Prospects</span>
                  <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
                </button>
                <p className="text-[10px] text-center text-muted-foreground flex items-center justify-center gap-1">
                  <ShieldCheck size={11} className="text-primary" /> No commitment • Cancel anytime • Includes Apollo & Apify waterfall
                </p>
              </div>
            </motion.div>
          )}

          <div className="border border-border/60 rounded-lg p-5 bg-gradient-to-r from-muted/50 to-muted/20 flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <ElesiumLogo size={16} />
                <h4 className="font-semibold text-sm">Elesium Data Hygiene</h4>
                <a href="https://elesium.online" target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary hover:underline font-semibold">(elesium.online)</a>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={cleanData} 
                  onChange={(e) => setCleanData(e.target.checked)} 
                  aria-label="Toggle Elesium Data Hygiene"
                  className="sr-only peer" 
                />
                <div className="w-11 h-6 bg-muted peer-focus:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">Clean messy data before it hits the database. Automatically removes emojis, fixes ALL CAPS formatting, and drops corporate suffixes like "LLC/Inc.".</p>
            <div className="text-[11px] text-muted-foreground flex justify-between mt-2 pt-2 border-t border-border/40">
              <span>Cost: {hygieneCost} credit{hygieneCost > 1 ? 's' : ''} ({detectedRowCount > 0 ? `${detectedRowCount.toLocaleString()} leads` : '100 leads / credit'})</span>
              <span className="font-medium">Balance: {billing?.data_cleaning_credits ?? '...'}</span>
            </div>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-6 animate-in fade-in max-w-2xl">
          {detectedRowCount > 50 && !isPro && (
            <div className="p-3.5 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-md bg-primary/20 text-primary">
                  <Rocket size={15} />
                </div>
                <div>
                  <span className="font-bold text-foreground block">
                    {detectedRowCount.toLocaleString()} prospects detected
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    Free Tier outreach is limited to 1 campaign.
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ 
                  campaignName: name || file?.name?.replace(/\.csv$/i, '') || "CSV Outreach", 
                  featureName: "Multi-Campaign Scale" 
                })}
                className="px-3 py-1.5 rounded-md bg-foreground text-background font-bold text-xs hover:opacity-90 transition-all shrink-0 flex items-center gap-1.5"
              >
                <span>Upgrade</span>
                <ArrowRight size={12} />
              </button>
            </div>
          )}

          {/* Column Mapping Section */}
          <div className="border border-border/60 rounded-lg overflow-hidden bg-background shadow-xs">
            <div className="px-4 py-3 bg-muted/30 border-b border-border/60 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <LayoutTemplate size={14} className="text-primary" />
                <span className="text-xs font-bold text-foreground">Map CSV Columns</span>
              </div>
              <span className="text-[11px] text-muted-foreground">
                Auto-matched with fuzzy detection
              </span>
            </div>

            {Object.entries({
              first_name: { label: "First Name", required: false, desc: "Used for personalized greetings {{first_name}}" },
              last_name: { label: "Last Name", required: false, desc: "Used for formal outreach" },
              full_name: { label: "Full Name (Auto-Split)", required: false, desc: "Auto-splits single column into First & Last Name" },
              linkedin_url: { label: "LinkedIn URL", required: !mappings.email, desc: "Required for automated connections & messages (or map Work Email)" },
              email: { label: "Work Email", required: !mappings.linkedin_url, desc: "Required for cold email sequences (or map LinkedIn URL)" },
              company_name: { label: "Company Name", required: false, desc: "Used for company variables {{company}}" },
              job_title: { label: "Job Title", required: false, desc: "Used for title variables {{job_title}}" },
              location: { label: "Location / City", required: false, desc: "Used for geographic variables" },
            }).map(([key, meta], i) => {
              const selectedCol = (mappings as any)[key]
              const sampleVal = sampleRows.length > 0 && selectedCol ? sampleRows[0][selectedCol] : null

              return (
                <div key={key} className={`flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-3 ${i !== 0 ? 'border-t border-border/50' : ''}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <label className="text-xs font-bold text-foreground flex items-center gap-1">
                        <span>{meta.label}</span>
                        {meta.required && <span className="text-rose-500 font-bold">*</span>}
                      </label>
                      {selectedCol && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold border border-emerald-500/20">
                          Mapped
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">{meta.desc}</p>
                    {sampleVal && (
                      <p className="text-[10px] text-primary font-mono truncate max-w-sm mt-0.5">
                        Sample: &quot;{sampleVal}&quot;
                      </p>
                    )}
                  </div>

                  <CustomSelect
                    value={selectedCol || ""}
                    onValueChange={val => setMappings({ ...mappings, [key]: val })}
                    size="sm"
                    className="w-full sm:w-56"
                    triggerClassName="h-9 text-xs bg-card border-input"
                    options={[
                      { value: "", label: "-- Ignore --" },
                      ...headers.map(h => ({ value: h, label: h }))
                    ]}
                  />
                </div>
              )
            })}
          </div>

          {/* Validation Status Radar */}
          {(() => {
            const linkedinCol = mappings.linkedin_url
            const emailCol = mappings.email

            if (!linkedinCol && !emailCol) {
              return (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex items-start gap-2.5">
                  <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold">Contact identifier required</p>
                    <p className="text-[11px] text-rose-700/80 dark:text-rose-300/80">
                      Please map at least one contact identifier column: <strong>LinkedIn URL</strong> (for LinkedIn outreach) or <strong>Work Email</strong> (for Email outreach).
                    </p>
                  </div>
                </div>
              )
            }

            if (!linkedinCol && emailCol) {
              return (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 dark:text-emerald-400 text-xs flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                    <span className="font-medium">
                      Email-First List mapped ({emailCol}) — Ready for Email Outreach
                    </span>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                    Ready to Import
                  </span>
                </div>
              )
            }

            const sampleUrls = sampleRows.map(r => r[linkedinCol!]).filter(Boolean)
            const hasValidLinkedinSample = sampleUrls.some(u => /linkedin\.com\/(in|pub|profile)/i.test(u) || u.startsWith("http"))

            if (sampleUrls.length > 0 && !hasValidLinkedinSample) {
              return (
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-xs flex items-start gap-2.5">
                  <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold">Format Warning on &quot;{linkedinCol}&quot;</p>
                    <p className="text-[11px] text-amber-800/80 dark:text-amber-300/80">
                      Sample rows do not match standard LinkedIn URLs (e.g. <code>https://linkedin.com/in/username</code>). Please verify column selection.
                    </p>
                  </div>
                </div>
              )
            }

            return (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 dark:text-emerald-400 text-xs flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                  <span className="font-medium">
                    Valid LinkedIn column selected ({sampleUrls.length > 0 ? sampleUrls[0] : "Ready"})
                    {emailCol && " + Work Email mapped"}
                  </span>
                </div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  Ready to Import
                </span>
              </div>
            )
          })()}

          {/* Pre-Flight 3-Row Sample Verification Table */}
          {sampleRows.length > 0 && (
            <div className="border border-border/80 rounded-lg overflow-hidden bg-card shadow-xs">
              <div className="px-4 py-2.5 bg-muted/40 border-b border-border/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Table size={13} className="text-primary" />
                  <span className="text-xs font-bold text-foreground">Pre-Flight Row Preview</span>
                </div>
                <span className="text-[10px] text-muted-foreground font-mono">
                  Showing first {Math.min(3, sampleRows.length)} rows
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-[11px] text-left border-collapse">
                  <thead>
                    <tr className="border-b border-border/50 text-muted-foreground bg-muted/20">
                      <th className="py-2 px-3 font-semibold w-8">#</th>
                      <th className="py-2 px-3 font-semibold">First Name</th>
                      <th className="py-2 px-3 font-semibold">Last Name</th>
                      <th className="py-2 px-3 font-semibold">Company</th>
                      <th className="py-2 px-3 font-semibold">LinkedIn URL</th>
                      <th className="py-2 px-3 font-semibold">Email</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sampleRows.slice(0, 3).map((row, idx) => {
                      const fname = mappings.first_name ? row[mappings.first_name] : null
                      const lname = mappings.last_name ? row[mappings.last_name] : null
                      const company = mappings.company_name ? row[mappings.company_name] : null
                      const url = mappings.linkedin_url ? row[mappings.linkedin_url] : null
                      const email = mappings.email ? row[mappings.email] : null

                      return (
                        <tr key={idx} className="border-b border-border/30 hover:bg-muted/30 transition-colors">
                          <td className="py-2 px-3 text-muted-foreground font-mono">{idx + 1}</td>
                          <td className="py-2 px-3 font-medium text-foreground">
                            {fname || <span className="text-muted-foreground italic">None (uses fallback)</span>}
                          </td>
                          <td className="py-2 px-3 text-foreground">{lname || "—"}</td>
                          <td className="py-2 px-3 text-foreground">{company || "—"}</td>
                          <td className="py-2 px-3 font-mono text-[10px] max-w-[200px] truncate text-primary">
                            {url || <span className="text-muted-foreground font-sans italic">—</span>}
                          </td>
                          <td className="py-2 px-3 font-mono text-[10px] max-w-[180px] truncate text-foreground">
                            {email || <span className="text-muted-foreground font-sans italic">—</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}
