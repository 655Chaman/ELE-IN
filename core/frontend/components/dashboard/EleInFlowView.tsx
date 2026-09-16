import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Link } from 'react-router-dom'
import { Users, Activity, Send, ArrowRight, Zap, Database, GitBranch } from 'lucide-react'

// Using the same flow steps from the original code
const FLOW_STEPS = [
  {
    id: 'accounts',
    stepNumber: 1,
    title: 'Connect Accounts',
    subtitle: 'Securely sync your LinkedIn profiles.',
    description: 'Our engine handles rate limits, warming, and IP rotation automatically. Add multiple sender accounts to scale your outreach effortlessly without triggering security alerts.',
    icon: Users,
    color: 'rgba(59, 130, 246, 0.15)',
    textColor: 'text-blue-500',
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
    color: 'rgba(16, 185, 129, 0.15)',
    textColor: 'text-emerald-500',
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
    color: 'rgba(139, 92, 246, 0.15)',
    textColor: 'text-violet-500',
    link: '/elein/campaigns',
    actionText: 'Create Campaign',
    stats: { label: 'AI Personalization', value: 'Enabled' }
  }
]

export function EleInFlowView() {
  // Manage which step is currently being viewed
  const [activeStepIndex, setActiveStepIndex] = useState(0)
  const [lastInteractionTime, setLastInteractionTime] = useState(Date.now())
  const stepData = FLOW_STEPS[activeStepIndex]

  const handleManualStep = (idx: number) => {
    setActiveStepIndex(idx)
    setLastInteractionTime(Date.now())
  }

  // Auto-advance the stepper. The timer resets whenever lastInteractionTime changes.
  useEffect(() => {
    let isMounted = true
    const timer = setInterval(() => {
      if (isMounted) setActiveStepIndex((prev) => (prev + 1) % FLOW_STEPS.length)
    }, 6000)
    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [lastInteractionTime])

  return (
    <motion.div
      key="flow-paginated"
      initial={{ opacity: 0, y: 20, filter: 'blur(8px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: -20, filter: 'blur(8px)' }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center justify-start min-h-[80vh] pt-12 pb-24 w-full"
    >
      <div className="flex flex-col items-center max-w-6xl mx-auto w-full px-4 space-y-12">
        
        {/* Header Section */}
        <div className="text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-500 text-sm font-medium">
            <Zap className="w-3.5 h-3.5" /> Automated Pipeline Engine
          </div>
          
          <h2 className="text-5xl md:text-6xl font-light tracking-tighter text-balance">
            Orchestrate your <span className="font-medium bg-clip-text text-transparent bg-gradient-to-r from-foreground to-foreground/50">outreach</span>
          </h2>
          
          <p className="text-muted-foreground text-xl max-w-2xl mx-auto leading-relaxed">
            Follow the three core steps to start generating continuous, automated pipeline on LinkedIn. Build, launch, and scale.
          </p>
        </div>

        {/* Interactive Flow Section */}
        <div className="flex flex-col lg:flex-row items-stretch justify-center gap-8 lg:gap-16 w-full mt-12 px-4 md:px-12">
          
          {/* Left Visualizer */}
          <div className="flex-1 max-w-md w-full aspect-square bg-card rounded-[40px] border border-border/50 flex items-center justify-center relative overflow-hidden shadow-2xl">
             {/* Subtle background glow based on active step */}
             <motion.div 
               className="absolute inset-0 blur-[100px] rounded-full opacity-30"
               animate={{ backgroundColor: stepData.color.replace('0.15', '0.6') }}
               transition={{ duration: 1 }}
             />
             
             {/* Framer motion handles the icon swapping smoothly */}
             <AnimatePresence mode="wait">
               <motion.div
                 key={activeStepIndex}
                 initial={{ opacity: 0, scale: 0.8, filter: 'blur(10px)' }}
                 animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
                 exit={{ opacity: 0, scale: 1.1, filter: 'blur(10px)' }}
                 transition={{ duration: 0.4 }}
                 className="relative z-10 w-48 h-48 rounded-full border border-border/50 bg-background/50 backdrop-blur-md flex items-center justify-center shadow-2xl"
               >
                  <stepData.icon className={`w-20 h-20 ${stepData.textColor} stroke-[1.5]`} />
                  
                  {/* Floating decorative elements */}
                  {stepData.id === 'accounts' && (
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2 }} className="absolute -top-2 -right-2 p-3 bg-blue-500/10 rounded-full border border-blue-500/20">
                      <Users size={20} className="text-blue-500" />
                    </motion.div>
                  )}
                  {stepData.id === 'leads' && (
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2 }} className="absolute bottom-0 -left-4 p-3 bg-emerald-500/10 rounded-xl border border-emerald-500/20">
                      <Database size={20} className="text-emerald-500" />
                    </motion.div>
                  )}
                  {stepData.id === 'campaigns' && (
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2 }} className="absolute -top-4 -left-4 p-3 bg-violet-500/10 rounded-lg border border-violet-500/20">
                      <GitBranch size={20} className="text-violet-500" />
                    </motion.div>
                  )}
               </motion.div>
             </AnimatePresence>
          </div>

          {/* Center Progress Node (Connector) - Hidden on mobile */}
          <div className="hidden lg:flex flex-col items-center justify-center relative">
              <div className="w-12 h-12 rounded-full border-4 border-border bg-background flex items-center justify-center z-10 shadow-lg">
                  <motion.div 
                    key={activeStepIndex}
                    initial={{ scale: 0.5 }}
                    animate={{ scale: 1 }}
                    className={`w-3 h-3 rounded-full ${stepData.textColor.replace('text-', 'bg-')}`} 
                  />
              </div>
          </div>

          {/* Right Content Card */}
          <div className="flex-1 max-w-md w-full flex flex-col justify-center">
            <Link to={stepData.link} className="block outline-none group h-full">
              <div className="bg-card border border-border/50 text-card-foreground rounded-[40px] overflow-hidden flex flex-col h-full shadow-2xl transition-all duration-300 hover:border-border hover:shadow-xl">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeStepIndex}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.3 }}
                    className="flex flex-col h-full"
                  >
                    <div className="space-y-6 pt-10 px-10">
                      <div className="flex justify-between items-center text-xs font-semibold text-muted-foreground uppercase tracking-widest">
                        <div className="w-12 h-12 rounded-2xl bg-muted/50 border border-border flex items-center justify-center">
                          <stepData.icon className="w-5 h-5 text-foreground/70" />
                        </div>
                        <span>STEP 0{stepData.stepNumber}</span>
                      </div>
                      
                      <div className="space-y-3">
                        <h3 className="text-3xl font-light tracking-tight">{stepData.title}</h3>
                        <p className="text-foreground/80 font-medium text-lg">{stepData.subtitle}</p>
                      </div>
                    </div>
                    
                    <div className="px-10 pb-8 pt-4 text-muted-foreground leading-relaxed text-[15px] flex-1">
                      {stepData.description}
                    </div>

                    <div className="mt-auto">
                      <div className="border-t border-border/50" />
                      <div className="px-10 py-6 flex justify-between items-center text-sm">
                        <div className="flex flex-col">
                          <span className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">{stepData.stats.label}</span>
                          <span className={`font-semibold text-base ${stepData.textColor}`}>
                            {stepData.stats.value}
                          </span>
                        </div>
                        <button className="text-muted-foreground hover:text-foreground flex items-center gap-2 uppercase text-xs font-semibold tracking-wider transition-colors group-hover:text-foreground">
                          {stepData.actionText} 
                          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                        </button>
                      </div>
                    </div>
                  </motion.div>
                </AnimatePresence>
              </div>
            </Link>

            {/* Manual Step Navigation */}
            <div className="flex justify-center gap-3 mt-8">
              {FLOW_STEPS.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => handleManualStep(idx)}
                  className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${
                    idx === activeStepIndex ? 'bg-foreground scale-125' : 'bg-border hover:bg-muted-foreground'
                  }`}
                  aria-label={`Go to step ${idx + 1}`}
                />
              ))}
            </div>
          </div>

        </div>
      </div>
    </motion.div>
  )
}

