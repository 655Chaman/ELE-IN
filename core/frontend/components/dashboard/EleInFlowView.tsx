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
      className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] py-8 lg:py-12 w-full"
    >
      <div className="flex flex-col items-center max-w-6xl mx-auto w-full px-4 space-y-12">
        
        {/* Header Section */}
        <div className="text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium">
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
        <div className="flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-16 w-full mt-12 px-4 md:px-12">
          
          {/* Left Visualizer */}
          <div className="flex-1 max-w-md w-full aspect-[4/3] lg:aspect-square bg-card/40 backdrop-blur-sm rounded-[40px] border border-white/5 flex items-center justify-center relative overflow-hidden shadow-[0_8px_40px_rgba(0,0,0,0.2)]">
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
                 initial={{ opacity: 0, y: 10, filter: 'blur(10px)' }}
                 animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                 exit={{ opacity: 0, y: -10, filter: 'blur(10px)' }}
                 transition={{ duration: 0.4 }}
                 className="relative z-10 w-full h-full p-8 flex flex-col items-center justify-center"
               >
                 {stepData.id === 'accounts' && (
                   <div className="w-full max-w-[260px] space-y-3">
                     {[1, 2, 3].map((i) => (
                       <motion.div 
                         key={i}
                         initial={{ opacity: 0, x: -20 }}
                         animate={{ opacity: 1, x: 0 }}
                         transition={{ delay: i * 0.1 }}
                         className="flex items-center gap-3 p-3 rounded-2xl bg-background/80 border border-white/5 shadow-sm"
                       >
                         <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center">
                           <Users size={18} className="text-blue-500" />
                         </div>
                         <div className="flex-1 space-y-1.5">
                           <div className="h-2.5 w-24 bg-foreground/20 rounded-full"></div>
                           <div className="h-2 w-16 bg-foreground/10 rounded-full"></div>
                         </div>
                         <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]"></div>
                       </motion.div>
                     ))}
                   </div>
                 )}

                 {stepData.id === 'leads' && (
                   <div className="w-full max-w-[280px] bg-background/80 rounded-2xl border border-white/5 shadow-lg overflow-hidden flex flex-col">
                     <div className="h-10 border-b border-white/5 flex items-center px-4 gap-2">
                       <Database size={14} className="text-emerald-500" />
                       <div className="h-2 w-16 bg-foreground/20 rounded-full"></div>
                     </div>
                     <div className="p-4 space-y-4">
                       {[1, 2, 3, 4].map((i) => (
                         <motion.div 
                           key={i}
                           initial={{ opacity: 0, scale: 0.95 }}
                           animate={{ opacity: 1, scale: 1 }}
                           transition={{ delay: i * 0.1 }}
                           className="flex items-center justify-between"
                         >
                           <div className="flex items-center gap-3">
                             <div className="w-6 h-6 rounded bg-emerald-500/20"></div>
                             <div className="space-y-1.5">
                               <div className="h-2 w-20 bg-foreground/20 rounded-full"></div>
                               <div className="h-1.5 w-12 bg-foreground/10 rounded-full"></div>
                             </div>
                           </div>
                           <div className="h-4 w-12 bg-foreground/5 rounded flex items-center justify-center">
                             <div className="h-1 w-8 bg-foreground/20 rounded-full"></div>
                           </div>
                         </motion.div>
                       ))}
                     </div>
                   </div>
                 )}

                 {stepData.id === 'campaigns' && (
                   <div className="w-full max-w-[260px] flex flex-col items-center">
                     <motion.div 
                       initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
                       className="p-3 rounded-2xl bg-background/80 border border-violet-500/30 flex items-center gap-3 shadow-lg w-full z-10"
                     >
                       <div className="p-2 bg-violet-500/20 rounded-lg"><Users size={16} className="text-violet-500"/></div>
                       <div className="h-2 w-20 bg-foreground/20 rounded-full"></div>
                     </motion.div>
                     
                     <div className="w-px h-6 bg-border"></div>
                     
                     <motion.div 
                       initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
                       className="p-3 rounded-2xl bg-background/80 border border-white/5 flex items-center gap-3 shadow-lg w-11/12 z-10"
                     >
                       <div className="p-2 bg-blue-500/20 rounded-lg"><Send size={16} className="text-blue-500"/></div>
                       <div className="h-2 w-24 bg-foreground/20 rounded-full"></div>
                     </motion.div>
                     
                     <div className="w-px h-6 bg-border"></div>
                     
                     <motion.div 
                       initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
                       className="p-3 rounded-2xl bg-background/80 border border-white/5 flex items-center gap-3 shadow-lg w-10/12 z-10"
                     >
                       <div className="p-2 bg-emerald-500/20 rounded-lg"><Activity size={16} className="text-emerald-500"/></div>
                       <div className="h-2 w-16 bg-foreground/20 rounded-full"></div>
                     </motion.div>
                   </div>
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
          <div className="flex-1 max-w-md w-full aspect-[4/3] lg:aspect-square flex flex-col justify-center">
            <Link to={stepData.link} className="block outline-none group w-full h-full">
              <div className="w-full h-full bg-card/80 backdrop-blur-2xl border border-white/10 text-card-foreground rounded-[40px] overflow-hidden flex flex-col shadow-[0_8px_40px_rgba(0,0,0,0.3)] transition-all duration-300 hover:border-white/20 hover:shadow-[0_16px_60px_rgba(0,0,0,0.4)]">
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


          </div>

        </div>
      </div>
    </motion.div>
  )
}

