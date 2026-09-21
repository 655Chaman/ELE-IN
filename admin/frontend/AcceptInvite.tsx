import { useEffect, useRef, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/lib/AuthContext"
import { fetchWithAuth } from "@/lib/apiClient"
import { CheckCircle2, XCircle, Loader2, ArrowRight } from "lucide-react"
import { motion } from "motion/react"
import { Button } from "@/components/ui/button"

export function AcceptInvite() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user, isLoading } = useAuth()
  
  const token = searchParams.get("token") || sessionStorage.getItem("pending_invite_token")
  
  const [status, setStatus] = useState<"loading" | "success" | "error" | "invalid">("loading")
  const [errorMessage, setErrorMessage] = useState("")
  const isAttempted = useRef(false)

  useEffect(() => {
    if (!token) {
      setStatus("invalid")
      return
    }

    if (isLoading) return

    if (!user) {
      sessionStorage.setItem("pending_invite_token", token)
      navigate("/login")
      return
    }

    if (isAttempted.current) return
    isAttempted.current = true

    const acceptInvite = async () => {
      try {
        const res = await fetchWithAuth("/api/workspaces/invites/accept", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        })

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}))
          throw new Error(errData.detail || "Failed to accept invite")
        }

        const data = await res.json()
        
        // Save the new workspace ID to switch context automatically
        if (data.workspace_id) {
          localStorage.setItem("elein_active_workspace", data.workspace_id)
        }

        sessionStorage.removeItem("pending_invite_token")
        setStatus("success")
        
        setTimeout(() => {
          navigate("/elein/campaigns")
        }, 2000)

      } catch (err: any) {
        setStatus("error")
        setErrorMessage("Failed to accept the invite — the link may have expired. Please request a new invitation.")
        sessionStorage.removeItem("pending_invite_token")
      }
    }

    acceptInvite()
  }, [token, user, isLoading, navigate])

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-[#070809] flex flex-col items-center justify-center p-4">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-500 mb-4" />
        <p className="text-zinc-400">Accepting invite...</p>
      </div>
    )
  }

  if (status === "invalid") {
    return (
      <div className="min-h-screen bg-[#070809] flex items-center justify-center p-4">
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 max-w-md w-full text-center"
        >
          <XCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <h2 className="text-xl font-medium text-white mb-2">Invalid Invite Link</h2>
          <p className="text-zinc-400 mb-6">This invite link is missing or malformed.</p>
          <Button onClick={() => navigate("/")} className="w-full">
            Go to Homepage <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </motion.div>
      </div>
    )
  }

  if (status === "error") {
    return (
      <div className="min-h-screen bg-[#070809] flex items-center justify-center p-4">
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 max-w-md w-full text-center"
        >
          <XCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <h2 className="text-xl font-medium text-white mb-2">Invite Failed</h2>
          <p className="text-zinc-400 mb-6">{errorMessage}</p>
          <Button onClick={() => navigate("/")} className="w-full">
            Go to Homepage <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#070809] flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 max-w-md w-full text-center"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", delay: 0.2 }}
        >
          <CheckCircle2 className="h-16 w-16 text-success mx-auto mb-6" />
        </motion.div>
        <h2 className="text-2xl font-semibold text-white mb-2">You're In!</h2>
        <p className="text-zinc-400">You've joined the workspace successfully. Redirecting...</p>
      </motion.div>
    </div>
  )
}
