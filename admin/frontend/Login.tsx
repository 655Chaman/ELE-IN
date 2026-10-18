import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { useAuth } from "@/lib/AuthContext"
import { Eye, EyeOff, Loader2, Sparkles, CheckCircle2, Shield, Zap } from "lucide-react"
import { motion, AnimatePresence } from "motion/react"

export function Login() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [companyName, setCompanyName] = useState("")
  const [isSignUp, setIsSignUp] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [errorMessage, setErrorMessage] = useState("")
  const [isResetting, setIsResetting] = useState(false)
  const [resetSent, setResetSent] = useState(false)
  const navigate = useNavigate()
  const { session } = useAuth()

  useEffect(() => {
    if (session) {
      const hasCompleted = localStorage.getItem("elein_has_completed_onboarding") === "true" || localStorage.getItem("onboarding_dismissed") === "true"
      navigate(hasCompleted ? '/elein/campaigns' : '/onboarding', { replace: true })
    }
  }, [session, navigate])

  const calculateStrength = (pass: string) => {
    let score = 0;
    if (pass.length >= 8) score++;
    if (/[A-Z]/.test(pass)) score++;
    if (/[0-9]/.test(pass)) score++;
    if (/[^A-Za-z0-9]/.test(pass)) score++;
    return score;
  }

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMessage("")
    
    if (isSignUp && !companyName.trim()) return setErrorMessage("Company name is required")
    if (!email.trim()) return setErrorMessage("Email is required")
    if (!password.trim()) return setErrorMessage("Password is required")
    
    if (isSignUp && password.length < 8) {
      return setErrorMessage("Password must be at least 8 characters long")
    }

    setIsLoading(true)
    try {
      if (isSignUp) {
        localStorage.setItem("ele_company_name", companyName.trim())
        const { data, error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        
        // C-02: Try to auto-create workspace if company name exists
        if (companyName.trim() && data.session?.access_token) {
          try {
            const wsRes = await fetch("/api/workspaces", {
              method: "POST",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${data.session.access_token}` },
              body: JSON.stringify({ name: companyName.trim() })
            })
            if (wsRes.ok) {
              const wsData = await wsRes.json().catch(() => ({}))
              if (wsData?.id) {
                localStorage.setItem("elein_active_workspace", wsData.id)
              }
              localStorage.removeItem("ele_company_name")
              localStorage.removeItem("ele_company_domain")
            }
          } catch (err) {
            console.error("Auto-create workspace on signup failed:", err)
          }
        }
        
        setErrorMessage("Check your email for the confirmation link, then sign in.")
        setIsSignUp(false)
      } else {
        const { data: signInData, error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error

        // If user has a pending company name from signup confirmation, create their initial workspace
        const savedCompany = localStorage.getItem("ele_company_name")
        const token = signInData.session?.access_token
        if (savedCompany && token) {
          try {
            const wsRes = await fetch("/api/workspaces", {
              method: "POST",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
              body: JSON.stringify({ name: savedCompany.trim() })
            })
            if (wsRes.ok) {
              const wsData = await wsRes.json().catch(() => ({}))
              if (wsData?.id) {
                localStorage.setItem("elein_active_workspace", wsData.id)
              }
              localStorage.removeItem("ele_company_name")
              localStorage.removeItem("ele_company_domain")
            }
          } catch (err) {
            console.error("Auto-create workspace on signin failed:", err)
          }
        }
        const hasCompleted = localStorage.getItem("elein_has_completed_onboarding") === "true" || localStorage.getItem("onboarding_dismissed") === "true"
        navigate(hasCompleted ? "/elein/campaigns" : "/onboarding")
      }
    } catch (error: any) {
      if (error.message.includes("fetch")) {
        setErrorMessage("Network error. Please check your connection.")
      } else {
        setErrorMessage(error.message || "Authentication failed. Please check your credentials.")
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleResetPassword = async () => {
    if (!email.trim()) return setErrorMessage("Enter your email address above to reset your password.")
    setIsResetting(true)
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email)
      if (error) throw error
      setResetSent(true)
      setTimeout(() => setResetSent(false), 30000)
    } catch (error: any) {
      setErrorMessage(error.message)
    } finally {
      setIsResetting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-background text-foreground font-sans">
      
      {/* Left Column: Product Showcase */}
      <div className="hidden lg:flex lg:w-[55%] relative overflow-hidden flex-col justify-between p-12 border-r border-border/40">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(var(--primary),0.08),transparent_50%)]" />
        <div className="absolute inset-0 bg-[url('/noise.png')] opacity-[0.03] mix-blend-overlay" />
        
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-white/80 backdrop-blur-md mb-8">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Ele-in v2.4 • Enterprise LinkedIn Outreach
          </div>
          <h1 className="text-4xl lg:text-5xl font-black text-white leading-[1.1] tracking-tight mb-6 max-w-xl">
            Automate LinkedIn pipeline with human-grade AI sequences.
          </h1>
          <p className="text-white/50 text-lg max-w-md leading-relaxed">
            Connect unlimited accounts, bypass restrictions safely, and let our agents book meetings for you on autopilot.
          </p>
        </div>

        {/* Sequence Preview Card */}
        <div className="relative z-10 w-full max-w-md bg-black/40 backdrop-blur-xl border border-white/10 rounded-xl p-6 shadow-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
              <Zap size={18} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-bold text-white">Live Campaign</p>
              <p className="text-xs text-white/50">Enterprise Founders • 420 Enrolled</p>
            </div>
          </div>
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="w-6 flex flex-col items-center">
                <div className="w-6 h-6 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-[10px] font-bold text-primary">1</div>
                <div className="w-px h-full bg-white/10 my-1" />
              </div>
              <div className="pb-4">
                <p className="text-sm font-medium text-white">Connection Request</p>
                <p className="text-xs text-white/50 mt-1">"Hey {'{{first_name}}'}, loved your recent post on..."</p>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="w-6 flex flex-col items-center">
                <div className="w-6 h-6 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-[10px] font-bold text-white/40">2</div>
                <div className="w-px h-full bg-white/10 my-1" />
              </div>
              <div className="pb-4 flex items-center gap-2">
                <p className="text-sm font-medium text-white">Smart Delay</p>
                <span className="text-[10px] bg-white/10 px-2 py-0.5 rounded text-white/60">2 Days</span>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="w-6 flex flex-col items-center">
                <div className="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-[10px] font-bold text-emerald-500"><CheckCircle2 size={12} /></div>
              </div>
              <div>
                <p className="text-sm font-medium text-white">Meeting Booked</p>
                <p className="text-xs text-emerald-500/80 mt-1">Goal achieved. Sequence paused.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex gap-6 mt-8 border-t border-white/10 pt-8">
          <div>
            <p className="text-2xl font-black text-white">38.4%</p>
            <p className="text-xs text-white/50 uppercase tracking-wider font-bold mt-1">Avg Conn. Rate</p>
          </div>
          <div>
            <p className="text-2xl font-black text-white">12k+</p>
            <p className="text-xs text-white/50 uppercase tracking-wider font-bold mt-1">Meetings Booked</p>
          </div>
          <div>
            <p className="text-2xl font-black text-white">0</p>
            <p className="text-xs text-white/50 uppercase tracking-wider font-bold mt-1">Account Bans</p>
          </div>
        </div>
      </div>

      {/* Right Column: Auth Card */}
      <div className="flex-1 flex flex-col justify-center items-center p-6 relative">
        <div className="w-full max-w-[400px]">
          
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-black text-white mb-2">{isSignUp ? "Create Workspace" : "Welcome Back"}</h2>
            <p className="text-sm text-white/50">{isSignUp ? "Start your 14-day free trial. No credit card required." : "Enter your credentials to access your pipeline."}</p>
          </div>

          <div className="flex bg-white/5 p-1 rounded-xl mb-8 border border-white/10">
            <button onClick={() => {setIsSignUp(false); setErrorMessage("");}} className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${!isSignUp ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white"}`}>Sign In</button>
            <button onClick={() => {setIsSignUp(true); setErrorMessage("");}} className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${isSignUp ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white"}`}>Create Account</button>
          </div>

          <form onSubmit={handleAuth} className="space-y-4">
            {isSignUp && (
              <div>
                <label className="block text-xs font-bold text-white/70 uppercase tracking-wider mb-2">Company Name</label>
                <input 
                  type="text" 
                  value={companyName} 
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                  placeholder="Acme Corp"
                  required
                />
              </div>
            )}
            <div>
              <label className="block text-xs font-bold text-white/70 uppercase tracking-wider mb-2">Work Email</label>
              <input 
                type="email" 
                autoComplete="email"
                value={email} 
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                placeholder="you@company.com"
                required
              />
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-xs font-bold text-white/70 uppercase tracking-wider">Password</label>
              </div>
              <div className="relative">
                <input 
                  type={showPassword ? "text" : "password"} 
                  autoComplete={isSignUp ? "new-password" : "current-password"}
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all pr-10"
                  placeholder="••••••••"
                  required
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white transition-colors">
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {isSignUp && password.length > 0 && (
                <div className="mt-3 flex gap-1">
                  {[1, 2, 3, 4].map(i => (
                    <div key={i} className={`h-1 flex-1 rounded-full ${calculateStrength(password) >= i ? (calculateStrength(password) > 2 ? 'bg-emerald-500' : 'bg-warning') : 'bg-white/10'}`} />
                  ))}
                </div>
              )}
            </div>

            <AnimatePresence>
              {errorMessage && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                  <div className={`p-3 rounded-xl text-sm font-medium mt-2 flex items-center gap-2 ${errorMessage.includes('confirmation') ? 'bg-success/10 text-success border border-success/20' : 'bg-destructive/10 text-destructive border border-destructive/20'}`}>
                    {errorMessage.includes('confirmation') ? <CheckCircle2 size={16} /> : <Shield size={16} />}
                    {errorMessage}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <button disabled={isLoading} className="w-full py-3.5 mt-4 bg-primary text-primary-foreground font-black rounded-xl hover:bg-primary/90 transition-all shadow-xs flex items-center justify-center gap-2 disabled:opacity-50">
              {isLoading ? <Loader2 size={18} className="animate-spin" /> : (isSignUp ? "Create Workspace" : "Sign In to Pipeline")}
            </button>
          </form>

          {!isSignUp && (
            <div className="mt-6 text-center">
              <button 
                type="button"
                onClick={handleResetPassword} 
                disabled={isResetting || resetSent}
                className="text-sm font-medium text-white/40 hover:text-white transition-colors disabled:opacity-50"
              >
                {resetSent ? "Reset link sent — check your email" : isResetting ? "Sending..." : "Forgot your password?"}
              </button>
            </div>
          )}

          <div className="mt-12 pt-6 border-t border-white/5 flex flex-col items-center">
             <button onClick={() => { setEmail('demo@ele-in.com'); setPassword('demo12345'); }} className="text-xs font-medium text-white/30 hover:text-white transition-colors bg-white/5 px-3 py-1.5 rounded-full border border-white/10">
               Auto-fill Demo Credentials
             </button>
          </div>

        </div>
      </div>
    </div>
  )
}
