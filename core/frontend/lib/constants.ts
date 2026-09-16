// All market configurations have been migrated to the backend database 
// and are fetched dynamically via the /api/pipelines/markets endpoint.
// This is a temporary stub to satisfy TS compiler for components not yet migrated.
export const MARKET_CONFIG: Record<string, any> = {
  hipaa: { 
    title: "HIPAA Penetration", 
    demandTarget: "Healthcare SaaS", 
    supplyTarget: "Compliance Auditors", 
    accent: "from-blue-500/20 to-cyan-500/10" 
  },
  defi: {
    title: "DeFi Security",
    demandTarget: "Web3 Protocols",
    supplyTarget: "Smart Contract Auditors",
    accent: "from-purple-500/20 to-pink-500/10"
  },
  ai: {
    title: "AI Infrastructure",
    demandTarget: "AI Startups",
    supplyTarget: "ML Ops Engineers",
    accent: "from-emerald-500/20 to-teal-500/10"
  }
}
