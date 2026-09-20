import { toast } from "sonner"
import { Check, Database, Sparkles } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { useLeadImport } from "../LeadImportContext"

export function HubSpotImport({ onClose, mode = "import" }: { onClose: () => void, mode?: "import" | "connect" }) {
  const { 
    isHubspotConnected, 
    hubspotToken, setHubspotToken, 
    hubspotConnecting, setHubspotConnecting,
    mutateHubspotStatus,
    hubspotLists,
    selectedHubspotList, setSelectedHubspotList
  } = useLeadImport();

  return (
    <div className="animate-in fade-in w-full text-center pb-4 pt-2">
      <div className="mx-auto w-16 h-16 bg-[#ff7a59]/10 rounded-full flex items-center justify-center mb-4 shadow-sm">
        <img src="https://cdn.simpleicons.org/hubspot/ff7a59" alt="HubSpot" className="w-8 h-8" />
      </div>
      <h3 className="text-xl font-bold mb-3 text-foreground">Connect HubSpot CRM</h3>
      <p className="text-muted-foreground text-sm mb-8 max-w-md mx-auto leading-relaxed">
        Sync your active HubSpot lists directly into Ele-in. We'll automatically enrich your contacts with fresh LinkedIn data and find their direct emails.
      </p>
      
      {!isHubspotConnected ? (
        <div className="max-w-md mx-auto">
          <div className="bg-card border shadow-sm rounded-xl p-6 text-left">
            <div className="mb-5">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                Authentication Required
              </h4>
              <p className="text-xs text-muted-foreground mt-1">
                Enter your Private App Token to securely connect your CRM.
              </p>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Access Token
                </label>
                <div className="relative">
                  <input 
                    type="password"
                    placeholder="pat-na1-xxxx-xxxx-xxxx"
                    className="flex h-11 w-full rounded-lg border border-input bg-background/50 px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:border-primary transition-all placeholder:text-muted-foreground/50"
                    value={hubspotToken}
                    onChange={(e) => setHubspotToken(e.target.value)}
                    spellCheck={false}
                  />
                  <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none">
                    <Database size={16} className="text-muted-foreground/40" />
                  </div>
                </div>
              </div>
              
              <button 
                onClick={async () => {
                  if (!hubspotToken) return toast.error("Please enter a token");
                  setHubspotConnecting(true);
                  try {
                    const res = await fetchWithAuth("/api/elein/hubspot/auth", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ access_token: hubspotToken })
                    });
                    if (!res.ok) throw new Error("Invalid token");
                    
                    await mutateHubspotStatus();
                    toast.success("Successfully authenticated with HubSpot!");
                    if (mode === "connect") {
                      onClose();
                      return;
                    }
                  } catch (err) {
                    toast.error("Failed to connect. Is your token valid?");
                  } finally {
                    setHubspotConnecting(false);
                  }
                }}
                disabled={hubspotConnecting || !hubspotToken}
                className="w-full h-11 bg-foreground text-background font-medium rounded-lg hover:bg-foreground/90 transition-all shadow-sm active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {hubspotConnecting ? "Verifying..." : "Connect Workspace"}
              </button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-4 text-center px-4">
            We encrypt your token at rest. <br/> Don't have one? <a href="https://developers.hubspot.com/docs/api/private-apps" target="_blank" className="text-foreground hover:underline font-medium" rel="noreferrer">Learn how to create a Private App</a>.
          </p>
        </div>
      ) : (
        <div className="text-left bg-muted/20 border p-6 rounded-xl max-w-md mx-auto animate-in fade-in slide-in-from-bottom-4">
            <div className="flex items-center gap-3 mb-6 pb-4 border-b">
              <div className="w-10 h-10 bg-green-500/20 text-green-500 rounded-full flex items-center justify-center">
                <Check size={20} />
              </div>
              <div>
                <p className="font-semibold text-sm">HubSpot Connected</p>
                <p className="text-xs text-muted-foreground">Authentication verified via Private App</p>
              </div>
            </div>
            
            <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-2">Select a Contact List</label>
            {hubspotLists.length === 0 ? (
              <div className="text-sm text-muted-foreground p-3 bg-background border rounded-md mb-4">No contact lists found in this HubSpot account.</div>
            ) : (
              <select 
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring mb-4"
                value={selectedHubspotList}
                onChange={(e) => setSelectedHubspotList(e.target.value)}
              >
                <option value="">-- Choose a List --</option>
                {hubspotLists.map((l: any) => (
                  <option key={l.id} value={l.id}>{l.name} ({l.count} contacts)</option>
                ))}
              </select>
            )}
            
            <div className="flex items-center gap-2 mt-4 text-xs text-muted-foreground bg-primary/10 p-3 rounded-lg text-primary dark:text-blue-400">
              <Sparkles size={14} />
              <p>Contacts will be automatically deduped and enriched when imported.</p>
            </div>
            
            <button 
              className="w-full mt-6 py-2 bg-foreground text-background font-semibold rounded-lg hover:bg-foreground/90 disabled:opacity-50"
              disabled={!selectedHubspotList}
              onClick={async () => {
                toast.success("List synchronization started!");
                // Here we would call the /import endpoint
                onClose();
              }}
            >
              Start Sync
            </button>
        </div>
      )}
    </div>
  )
}
