import { motion } from "motion/react"
import { CreditCard, Zap, CheckCircle2, CircleDollarSign } from "lucide-react"
import SpotlightCard from "@/components/SpotlightCard"
import ShinyText from "@/components/ShinyText"

export function EleInBilling() {
  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-6xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <CreditCard size={24} className="text-primary" />
            <ShinyText text="Billing & Subscription" disabled={false} speed={3} className="" />
          </h1>
          <p className="text-xs text-muted-foreground">Manage your credits, invoices, and upgrade your subscription plan.</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <SpotlightCard className="col-span-2 p-6 rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2 text-muted-foreground">
              <Zap size={16} className="text-amber-500" /> 
              <span className="text-xs font-semibold uppercase tracking-wider">Current Plan</span>
            </div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground mb-1">Growth Tier</h2>
            <p className="text-sm text-muted-foreground mb-4">You have access to advanced sequencing, custom integrations, and priority curation.</p>
          </div>
          <div className="flex items-center gap-3">
            <button className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-sm font-bold transition-all shadow-sm">
              Upgrade Plan
            </button>
            <button className="px-4 py-2 bg-background hover:bg-muted border border-border/50 text-foreground rounded-lg text-sm font-bold transition-all shadow-sm">
              Cancel Subscription
            </button>
          </div>
        </SpotlightCard>
        
        <SpotlightCard className="p-6 rounded-2xl border border-primary/20 bg-primary/5 backdrop-blur-md flex flex-col items-center justify-center text-center">
          <CircleDollarSign size={32} className="text-primary mb-3" />
          <h3 className="text-4xl font-bold text-foreground tracking-tighter mb-1">2,450</h3>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-4">Credits Remaining</p>
          <button className="w-full px-4 py-2 bg-primary/10 hover:bg-primary/20 border border-primary/20 text-primary rounded-lg text-sm font-bold transition-all shadow-sm">
            Buy More Credits
          </button>
        </SpotlightCard>
      </div>

      <h2 className="text-lg font-bold text-foreground mb-4">Billing History</h2>
      <SpotlightCard className="rounded-2xl border border-border/50 bg-muted/10 backdrop-blur-md overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/50 border-b border-border/50 text-xs text-muted-foreground uppercase tracking-wider">
            <tr>
              <th className="px-6 py-3 font-semibold">Date</th>
              <th className="px-6 py-3 font-semibold">Description</th>
              <th className="px-6 py-3 font-semibold">Amount</th>
              <th className="px-6 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            <tr>
              <td className="px-6 py-4 text-foreground">Aug 01, 2026</td>
              <td className="px-6 py-4 text-foreground">Growth Tier - Monthly</td>
              <td className="px-6 py-4 text-foreground">$149.00</td>
              <td className="px-6 py-4">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                  <CheckCircle2 size={12} /> Paid
                </span>
              </td>
            </tr>
            <tr>
              <td className="px-6 py-4 text-foreground">Jul 15, 2026</td>
              <td className="px-6 py-4 text-foreground">1,000 Extra Credits</td>
              <td className="px-6 py-4 text-foreground">$29.00</td>
              <td className="px-6 py-4">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                  <CheckCircle2 size={12} /> Paid
                </span>
              </td>
            </tr>
            <tr>
              <td className="px-6 py-4 text-foreground">Jul 01, 2026</td>
              <td className="px-6 py-4 text-foreground">Growth Tier - Monthly</td>
              <td className="px-6 py-4 text-foreground">$149.00</td>
              <td className="px-6 py-4">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                  <CheckCircle2 size={12} /> Paid
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </SpotlightCard>
    </div>
  )
}
