import Papa from "papaparse"
import { Download, LayoutTemplate, Sparkles, Upload } from "lucide-react"
import { useLeadImport } from "../LeadImportContext"

export function CSVImport() {
  const { 
    step, 
    file, setFile, 
    cleanData, setCleanData, 
    headers, setHeaders, 
    mappings, setMappings, 
    billing, 
    fileInputRef 
  } = useLeadImport();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      Papa.parse(selected, {
        header: true,
        preview: 1,
        complete: (results: any) => {
          if (results.meta.fields) {
            const fields: string[] = results.meta.fields;
            setHeaders(fields);
            const guess = (keywords: string[]) => fields.find((f: string) => keywords.some((k: string) => f.toLowerCase().includes(k))) || "";
            setMappings({
              first_name: guess(['first', 'fname']),
              last_name: guess(['last', 'lname']),
              linkedin_url: guess(['linkedin', 'url', 'profile']),
              company_name: guess(['company', 'org'])
            });
          }
        }
      });
    }
  }

  return (
    <>
      {step === 1 && (
        <div className="animate-in fade-in max-w-xl space-y-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">Upload CSV File</label>
              <a href="/template_leads.csv" download className="text-xs text-primary hover:underline flex items-center gap-1"><Download size={12} /> Download template</a>
            </div>
            <div className="border-dashed border-2 border-border hover:border-primary/70 hover:bg-primary/5 rounded-xl p-10 flex flex-col items-center gap-3 transition-all cursor-pointer bg-muted/20 group" onClick={() => fileInputRef.current?.click()}>
              <input type="file" ref={fileInputRef} className="hidden" accept=".csv" onChange={handleFileChange} />
              <div className="p-5 rounded-2xl bg-background border shadow-sm group-hover:scale-105 transition-transform"><Upload size={24} className="text-foreground" /></div>
              <div className="text-center">
                <p className="text-sm font-semibold">{file ? <span className="text-primary">{file.name}</span> : "Click to browse or drag CSV here"}</p>
                <p className="text-xs font-medium text-muted-foreground mt-1">Max 50MB · CSV only</p>
                <p className="text-[10px] text-muted-foreground mt-1">Supports: First Name, Last Name, LinkedIn, Company</p>
              </div>
            </div>
          </div>
          <div className="border rounded-xl p-5 bg-gradient-to-r from-muted/50 to-muted/20 flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2"><Sparkles size={18} className="text-primary" /><h4 className="font-semibold text-sm">AI Data Hygiene</h4></div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" checked={cleanData} onChange={(e) => setCleanData(e.target.checked)} className="sr-only peer" />
                <div className="w-11 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">Clean messy data before it hits the database. Automatically removes emojis, fixes ALL CAPS formatting, and drops corporate suffixes like "LLC/Inc.".</p>
            <div className="text-[11px] text-muted-foreground flex justify-between mt-2 pt-2 border-t">
              <span>Cost: 1 credit / 100 leads</span>
              <span className="font-medium">Balance: {billing?.data_cleaning_credits ?? 1000}</span>
            </div>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-6 animate-in fade-in max-w-xl">
          <div className="border rounded-xl overflow-hidden bg-background shadow-sm">
            {Object.entries({ first_name: "First Name", last_name: "Last Name", linkedin_url: "LinkedIn URL (Required)", company_name: "Company Name" }).map(([key, label], i) => (
              <div key={key} className={`flex justify-between items-center p-4 ${i !== 0 ? 'border-t' : ''}`}>
                <div className="flex items-center gap-3 text-sm">
                  <div className="p-2 rounded bg-muted"><LayoutTemplate size={16} className="text-muted-foreground" /></div>
                  <label className="font-medium">{label}</label>
                </div>
                <select value={(mappings as any)[key]} onChange={e => setMappings({...mappings, [key]: e.target.value})} className="flex h-10 w-56 rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                  <option value="">-- Ignore --</option>
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
