import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Users, Activity, Send, ArrowRight, Database } from 'lucide-react'

// Using the same flow steps from the original code
const FLOW_STEPS = [
  {
    id: 'accounts',
    stepNumber: 1,
    title: 'Connect Accounts',
    subtitle: 'Securely sync your LinkedIn profiles.',
    description: 'Our engine handles rate limits, warming, and IP rotation automatically. Add multiple sender accounts to scale your outreach effortlessly without triggering security alerts.',
    icon: Users,
    color: 'hsl(var(--primary))',
    textColor: 'text-primary',
    link: '/elein/accounts',
    actionText: 'Manage Accounts',
    stats: { label: 'Engine Status', value: 'Ready to Sync' }
  },
  {
    id: 'leads',
    stepNumber: 2,
    title: 'Import Leads',
    subtitle: 'Feed the engine with high-quality prospects.',
    description: 'Import prospects via CSV, Sales Navigator URLs, or direct API integration. Our system automatically cleans, enriches, and deduplicates your list before sending.',
    icon: Activity,
    color: 'hsl(var(--primary))',
    textColor: 'text-primary',
    link: '/elein/leads',
    actionText: 'Upload Data',
    stats: { label: 'Auto Enrichment', value: 'Active' }
  },
  {
    id: 'campaigns',
    stepNumber: 3,
    title: 'Launch Campaigns',
    subtitle: 'Build sequences and ignite automation.',
    description: 'Design multi-touch sequences, set intelligent delays, and let AI personalize your messages. A/B test your copy and watch the meetings roll in on autopilot.',
    icon: Send,
    color: 'hsl(var(--primary))',
    textColor: 'text-primary',
    link: '/elein/campaigns',
    actionText: 'Create Campaign',
    stats: { label: 'AI Personalization', value: 'Enabled' }
  }
]

export function EleInFlowView() {
  const [activeStepIndex, setActiveStepIndex] = useState(0)
  const stepData = FLOW_STEPS[activeStepIndex]

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] py-8 lg:py-12 w-full">
      <div className="flex flex-col items-center max-w-6xl mx-auto w-full px-4 space-y-10">
        
        {/* Header Section */}
        <div className="text-center space-y-4">
          <h2 className="text-4xl md:text-5xl font-light tracking-tight text-foreground">
            Orchestrate your <span className="font-medium text-foreground">outreach</span>
          </h2>
          
          <p className="text-muted-foreground text-base max-w-2xl mx-auto leading-relaxed">
            Follow the three core steps to start generating continuous, automated pipeline on LinkedIn. Build, launch, and scale.
          </p>

          {/* Step Selector Pills */}
          <div className="inline-flex items-center gap-1.5 p-1 bg-muted/60 rounded-xl border border-border mt-2">
            {FLOW_STEPS.map((step, idx) => (
              <button
                key={step.id}
                onClick={() => setActiveStepIndex(idx)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 ${
                  activeStepIndex === idx
                    ? 'bg-card text-foreground shadow-xs border border-border'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <span className="w-4 h-4 rounded-full bg-primary/10 text-primary flex items-center justify-center text-[10px] font-mono">
                  {idx + 1}
                </span>
                <span>{step.title}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Interactive Flow Section */}
        <div className="flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-12 w-full mt-6 px-4 md:px-12">
          
          {/* Left Visualizer */}
          <div className="flex-1 max-w-md w-full aspect-[4/3] lg:aspect-square bg-card rounded-xl border border-border flex items-center justify-center relative overflow-hidden shadow-xs">
            <div className="relative z-10 w-full h-full p-8 flex flex-col items-center justify-center">
              {stepData.id === 'accounts' && (
                <div className="w-full max-w-[260px] space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div 
                      key={i}
                      className="flex items-center gap-3 p-3 rounded-xl bg-background border border-border shadow-xs"
                    >
                      <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                        <Users size={18} className="text-primary" />
                      </div>
                      <div className="flex-1 space-y-1.5">
                        <div className="h-2.5 w-24 bg-foreground/20 rounded-full"></div>
                        <div className="h-2 w-16 bg-foreground/10 rounded-full"></div>
                      </div>
                      <div className="w-2 h-2 rounded-full bg-primary"></div>
                    </div>
                  ))}
                </div>
              )}

              {stepData.id === 'leads' && (
                <div className="w-full max-w-[280px] bg-background rounded-xl border border-border shadow-xs overflow-hidden flex flex-col">
                  <div className="h-10 border-b border-border flex items-center px-4 gap-2">
                    <Database size={14} className="text-primary" />
                    <div className="h-2 w-16 bg-foreground/20 rounded-full"></div>
                  </div>
                  <div className="p-4 space-y-4">
                    {[1, 2, 3, 4].map((i) => (
                      <div 
                        key={i}
                        className="flex items-center justify-between"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-6 h-6 rounded bg-primary/20"></div>
                          <div className="space-y-1.5">
                            <div className="h-2 w-20 bg-foreground/20 rounded-full"></div>
                            <div className="h-1.5 w-12 bg-foreground/10 rounded-full"></div>
                          </div>
                        </div>
                        <div className="h-4 w-12 bg-foreground/5 rounded flex items-center justify-center">
                          <div className="h-1 w-8 bg-foreground/20 rounded-full"></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {stepData.id === 'campaigns' && (
                <div className="w-full max-w-[260px] flex flex-col items-center">
                  <div className="p-3 rounded-xl bg-background border border-border flex items-center gap-3 shadow-xs w-full z-10">
                    <div className="p-2 bg-primary/10 rounded-xl"><Users size={16} className="text-primary"/></div>
                    <div className="h-2 w-20 bg-foreground/20 rounded-full"></div>
                  </div>
                  
                  <div className="w-px h-6 bg-border"></div>
                  
                  <div className="p-3 rounded-xl bg-background border border-border flex items-center gap-3 shadow-xs w-11/12 z-10">
                    <div className="p-2 bg-primary/10 rounded-xl"><Send size={16} className="text-primary"/></div>
                    <div className="h-2 w-24 bg-foreground/20 rounded-full"></div>
                  </div>
                  
                  <div className="w-px h-6 bg-border"></div>
                  
                  <div className="p-3 rounded-xl bg-background border border-border flex items-center gap-3 shadow-xs w-10/12 z-10">
                    <div className="p-2 bg-primary/10 rounded-xl"><Activity size={16} className="text-primary"/></div>
                    <div className="h-2 w-16 bg-foreground/20 rounded-full"></div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Center Connector Indicator */}
          <div className="hidden lg:flex flex-col items-center justify-center">
            <div className="w-10 h-10 rounded-full border border-border bg-card flex items-center justify-center shadow-xs">
              <span className="text-xs font-mono font-bold text-primary">0{stepData.stepNumber}</span>
            </div>
          </div>

          {/* Right Content Card */}
          <div className="flex-1 max-w-md w-full aspect-[4/3] lg:aspect-square flex flex-col justify-center">
            <Link to={stepData.link} className="block outline-none group w-full h-full">
              <div className="w-full h-full bg-card border border-border text-card-foreground rounded-xl overflow-hidden flex flex-col shadow-xs transition-colors hover:border-foreground/20">
                <div className="flex flex-col h-full">
                  <div className="space-y-4 pt-8 px-8">
                    <div className="flex justify-between items-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      <div className="w-10 h-10 rounded-xl bg-muted/60 border border-border flex items-center justify-center">
                        <stepData.icon className="w-5 h-5 text-foreground/70" />
                      </div>
                      <span>STEP 0{stepData.stepNumber}</span>
                    </div>
                    
                    <div className="space-y-1.5">
                      <h3 className="text-2xl font-semibold tracking-tight text-foreground">{stepData.title}</h3>
                      <p className="text-foreground/80 font-medium text-sm">{stepData.subtitle}</p>
                    </div>
                  </div>
                  
                  <div className="px-8 pb-6 pt-3 text-muted-foreground leading-relaxed text-xs flex-1">
                    {stepData.description}
                  </div>

                  <div className="mt-auto border-t border-border">
                    <div className="px-8 py-4 flex justify-between items-center text-xs">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">{stepData.stats.label}</span>
                        <span className={`font-semibold text-sm ${stepData.textColor}`}>
                          {stepData.stats.value}
                        </span>
                      </div>
                      <span className="text-primary hover:underline flex items-center gap-1.5 uppercase text-xs font-semibold tracking-wider">
                        <span>{stepData.actionText}</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </Link>
          </div>

        </div>
      </div>
    </div>
  )
}
