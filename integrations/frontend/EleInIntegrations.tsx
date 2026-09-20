import { motion } from "motion/react"
import { Plug, Zap, CheckCircle2, Search, ArrowRight, ExternalLink, Settings, X } from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"
import useSWR from "swr"
import { fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { useState } from "react"
import { LeadImportProvider } from "@/components/leads/LeadImportContext"
import { HubSpotImport } from "@/components/leads/methods/HubSpotImport"

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

const BASE_INTEGRATIONS = [
  { id: "hubspot", name: "HubSpot", category: "CRM", description: "Sync leads, campaigns, and activity data directly to HubSpot.", status: "available" },
  { id: "salesforce", name: "Salesforce", category: "CRM", description: "Bidirectional sync for leads, opportunities, and accounts.", status: "coming_soon" },
  { id: "slack", name: "Slack", category: "Communication", description: "Get real-time alerts for replies, meetings booked, and bounces.", status: "coming_soon" },
  { id: "zapier", name: "Zapier", category: "Automation", description: "Connect Ele-in with 5,000+ apps using custom Zapier workflows.", status: "coming_soon" },
  { id: "webhook", name: "Custom Webhooks", category: "Developer", description: "Receive real-time event payloads to your custom endpoints.", status: "coming_soon" }
]

export function EleInIntegrations() {
  const { data: hubspotStatus } = useSWR("/api/elein/hubspot/status", fetcher);

  const integrations = BASE_INTEGRATIONS.map(app => {
    if (app.id === "hubspot" && hubspotStatus?.connected) {
      return { ...app, status: "connected" };
    }
    return app;
  });

  const [showHubspotModal, setShowHubspotModal] = useState(false);

  const handleConnect = (id: string) => {
    if (id !== "hubspot") {
      toast("Coming soon — we'll notify you when this integration launches");
    } else {
      setShowHubspotModal(true);
    }
  }

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-6xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Plug size={24} className="text-primary" />
            <ShinyText text="Integrations" disabled={false} speed={3} className="" />
          </h1>
          <p className="text-xs text-muted-foreground">Connect Ele-in to your CRM and workflow tools to keep your data perfectly in sync.</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {integrations.map((app, i) => (
          <motion.div
            key={app.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <SpotlightCard className="h-full flex flex-col p-6 rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md hover:border-border transition-all">
              <div className="flex justify-between items-start mb-4">
                <div className="w-12 h-12 rounded-2xl bg-background border border-border/50 flex items-center justify-center">
                  <Zap size={20} className="text-primary opacity-80" />
                </div>
                {app.status === "connected" ? (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                    <CheckCircle2 size={12} /> Connected
                  </span>
                ) : app.status === "coming_soon" ? (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50 text-muted-foreground text-[10px] font-bold">
                    Coming Soon
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-muted-foreground text-[10px] font-bold">
                    Available
                  </span>
                )}
              </div>
              
              <h3 className="text-base font-bold text-foreground tracking-tight mb-1">
                {app.name}
              </h3>
              <p className="text-[10px] font-semibold text-primary/80 mb-3 tracking-wider uppercase">
                {app.category}
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6 flex-1">
                {app.description}
              </p>

              <div className="pt-4 border-t border-border/50 mt-auto">
                {app.status === "connected" ? (
                  <button className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-background hover:bg-muted border border-border/50 rounded-lg text-xs font-bold text-foreground transition-all shadow-sm">
                    <Settings size={14} className="text-muted-foreground" /> Manage
                  </button>
                ) : app.status === "coming_soon" ? (
                  <button disabled className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-muted text-muted-foreground rounded-lg text-xs font-bold cursor-not-allowed opacity-70">
                    Connect
                  </button>
                ) : (
                  <button onClick={() => handleConnect(app.id)} className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-bold transition-all shadow-sm">
                    Connect
                  </button>
                )}
              </div>
            </SpotlightCard>
          </motion.div>
        ))}
      </div>

      {showHubspotModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="bg-card w-full max-w-md rounded-2xl border shadow-xl p-6 relative">
            <button 
              onClick={() => setShowHubspotModal(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground z-10"
            >
              <X size={20} />
            </button>
            <LeadImportProvider>
              <HubSpotImport onClose={() => setShowHubspotModal(false)} mode="connect" />
            </LeadImportProvider>
          </div>
        </div>
      )}
    </div>
  )
}
