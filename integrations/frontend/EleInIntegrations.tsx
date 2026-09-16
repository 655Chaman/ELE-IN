import { motion } from "motion/react"
import { Plug, Zap, CheckCircle2, Search, ArrowRight, ExternalLink, Settings } from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"
import useSWR from "swr"
import { fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

const BASE_INTEGRATIONS = [
  { id: "hubspot", name: "HubSpot", category: "CRM", description: "Sync leads, campaigns, and activity data directly to HubSpot.", status: "available" },
  { id: "salesforce", name: "Salesforce", category: "CRM", description: "Bidirectional sync for leads, opportunities, and accounts.", status: "available" },
  { id: "slack", name: "Slack", category: "Communication", description: "Get real-time alerts for replies, meetings booked, and bounces.", status: "available" },
  { id: "zapier", name: "Zapier", category: "Automation", description: "Connect Ele-in with 5,000+ apps using custom Zapier workflows.", status: "available" },
  { id: "webhook", name: "Custom Webhooks", category: "Developer", description: "Receive real-time event payloads to your custom endpoints.", status: "available" }
]

export function EleInIntegrations() {
  const { data: hubspotStatus } = useSWR("/api/elein/hubspot/status", fetcher);

  const integrations = BASE_INTEGRATIONS.map(app => {
    if (app.id === "hubspot" && hubspotStatus?.is_connected) {
      return { ...app, status: "connected" };
    }
    return app;
  });

  const handleConnect = (id: string) => {
    if (id !== "hubspot") {
      toast("Coming soon — we'll notify you when this integration launches");
    } else {
      // Connect hubspot logic if any, or just toast for now
      toast("HubSpot connection flow initiated");
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
    </div>
  )
}
