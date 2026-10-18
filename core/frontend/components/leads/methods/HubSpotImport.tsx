import { useState } from "react"
import { toast } from "sonner"
import { Check, Database, Sparkles, Lock, Zap, Loader2 } from "lucide-react"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import useSWR from "swr"
import { useLeadImport } from "../LeadImportContext"
import { CustomSelect } from "@/components/ui/select"

export function HubSpotImport({ onClose, mode = "import" }: { onClose: () => void, mode?: "import" | "connect" }) {
  const { 
    isHubspotConnected, 
    hubspotToken, setHubspotToken, 
    hubspotConnecting, setHubspotConnecting,
    mutateHubspotStatus,
    hubspotLists,
    selectedHubspotList, setSelectedHubspotList
  } = useLeadImport();

  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const tier = billingData?.tier || 'FREE';
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE';
  const [isSyncing, setIsSyncing] = useState(false);

  return (
    <div className="animate-in fade-in w-full text-center pb-4 pt-2">
      <div className="mx-auto w-16 h-16 bg-orange-500/10 rounded-full flex items-center justify-center mb-4 shadow-xs">
        <img src="https://cdn.simpleicons.org/hubspot/ff7a59" alt="HubSpot" className="w-8 h-8" />
      </div>
      <div className="flex items-center justify-center gap-2 mb-2">
        <h3 className="text-xl font-bold text-foreground">Connect HubSpot CRM</h3>
        {!isPro && (
          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30 flex items-center gap-1">
            <Lock size={10} /> Pro
          </span>
        )}
      </div>
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
              
              {!isPro ? (
                <button 
                  onClick={() => {
                    openPaywall({ featureName: "HubSpot CRM Integration" });
                    toast.info("HubSpot CRM integration requires Growth Pro.");
                  }}
                  className="w-full h-11 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition-colors shadow-xs flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Lock size={14} />
                  <span>Unlock with Growth Pro</span>
                </button>
              ) : (
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
                      if (res.status === 403) {
                        openPaywall({ featureName: "HubSpot CRM Integration" });
                        toast.info("HubSpot CRM integration requires Growth Pro.");
                        return;
                      }
                      if (!res.ok) throw new Error("Invalid token");
                      
                      await mutateHubspotStatus();
                      toast.success("Successfully authenticated with HubSpot!");
                      if (mode === "connect") {
                        onClose();
                        return;
                      }
                    } catch (err: any) {
                      toast.error("Failed to connect. Is your token valid?");
                    } finally {
                      setHubspotConnecting(false);
                    }
                  }}
                  disabled={hubspotConnecting || !hubspotToken}
                  className="w-full h-11 bg-foreground text-background font-medium rounded-lg hover:bg-foreground/90 transition-colors shadow-xs disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
                >
                  {hubspotConnecting ? "Verifying..." : "Connect Workspace"}
                </button>
              )}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-4 text-center px-4">
            We encrypt your token at rest. <br/> Don't have one? <a href="https://developers.hubspot.com/docs/api/private-apps" target="_blank" className="text-foreground hover:underline font-medium" rel="noopener noreferrer">Learn how to create a Private App</a>.
          </p>
        </div>
      ) : (
        <div className="text-left bg-muted/20 border p-6 rounded-xl max-w-md mx-auto animate-in fade-in slide-in-from-bottom-4">
            <div className="flex items-center gap-3 mb-6 pb-4 border-b">
              <div className="w-10 h-10 bg-success/20 text-success rounded-full flex items-center justify-center">
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
              <CustomSelect 
                className="mb-4 text-left"
                value={selectedHubspotList}
                onValueChange={setSelectedHubspotList}
                placeholder="-- Choose a List --"
                triggerClassName="h-10 text-sm bg-background border-input"
                options={[
                  { value: "", label: "-- Choose a List --" },
                  ...hubspotLists.map((l: any) => ({
                    value: l.id,
                    label: `${l.name} (${l.count} contacts)`
                  }))
                ]}
              />
            )}
            
            <div className="flex items-center gap-2 mt-4 text-xs text-muted-foreground bg-primary/10 p-3 rounded-lg text-primary dark:text-primary">
              <Sparkles size={14} />
              <p>Contacts will be automatically deduped and enriched when imported.</p>
            </div>
            
            {!isPro ? (
              <button
                type="button"
                className="w-full mt-6 py-2.5 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 flex items-center justify-center gap-2 cursor-pointer shadow-xs"
                onClick={() => {
                  openPaywall({ featureName: "HubSpot CRM Integration" });
                  toast.info("HubSpot CRM integration requires Growth Pro.");
                }}
              >
                <Lock size={14} />
                <span>Unlock HubSpot Sync with Pro</span>
              </button>
            ) : (
              <button 
                type="button"
                className="w-full mt-6 py-2.5 bg-foreground text-background font-semibold rounded-lg hover:bg-foreground/90 disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer transition-all shadow-xs"
                disabled={!selectedHubspotList || isSyncing}
                onClick={async () => {
                  if (!selectedHubspotList) {
                    toast.error("Please select a HubSpot contact list");
                    return;
                  }
                  setIsSyncing(true);
                  try {
                    const res = await fetchWithAuth(`/api/elein/hubspot/import?list_id=${encodeURIComponent(selectedHubspotList)}`, {
                      method: "POST"
                    });
                    if (res.status === 403) {
                      openPaywall({ featureName: "HubSpot CRM Integration" });
                      toast.info("HubSpot CRM integration requires Growth Pro.");
                      return;
                    }
                    if (!res.ok) {
                      const errData = await res.json().catch(() => ({}));
                      throw new Error(errData.detail || "Failed to trigger HubSpot sync");
                    }
                    toast.success("HubSpot list import started in the background! Leads will appear shortly.");
                    onClose();
                  } catch (err: any) {
                    toast.error(err.message || "Failed to start HubSpot sync. Please check your connection.");
                  } finally {
                    setIsSyncing(false);
                  }
                }}
              >
                {isSyncing ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    <span>Initiating Sync...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={15} />
                    <span>Start Sync</span>
                  </>
                )}
              </button>
            )}
        </div>
      )}
    </div>
  )
}
