import { Routes, Route, useNavigate, Navigate } from "react-router-dom"
import { Toaster } from "sonner"
import { useEffect } from "react"
import { AppLayout } from "./components/AppLayout"
import { ChatInterface } from "./core/layout/ChatInterface"

import { EleInDashboard } from "@dashboard/EleInDashboard"
import { EleInAccounts } from "@accounts/EleInAccounts"
import { EleInLeads } from "@leads/EleInLeads"
import { EleInCampaigns } from "@campaigns/EleInCampaigns"
import { EleInCreateCampaign } from "@campaigns/EleInCreateCampaign"
import { EleInCampaignDetail } from "@campaigns/EleInCampaignDetail"
import { EleInInbox } from "@inbox/EleInInbox"
import { EleInTemplates } from "./core/layout/EleInTemplates"
import EleInKnowledge from "@knowledge/EleInKnowledge"
import { EleInWelcome } from "@admin/EleInWelcome"
 
import { ThemeProvider } from "./components/ThemeProvider"
import { AuthProvider, useAuth } from "./lib/AuthContext"
import { Login } from "@admin/Login"
import { AcceptInvite } from "@admin/AcceptInvite"
 
import { EleInAdmin } from "@admin/EleInAdmin"
import { EleInIntegrations } from "@integrations/EleInIntegrations"
import { EleInSettings } from "@admin/EleInSettings"
import { EleInAgencySettings } from "@admin/EleInAgencySettings"
import { EleInBilling } from "@admin/EleInBilling"
import { MFASetupPage } from "@admin/MFASetupPage"

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();
  
  if (isLoading) {
    return <div className="min-h-screen bg-[#070809] flex items-center justify-center text-zinc-500">Loading...</div>;
  }
  
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
}

import { WorkspaceProvider } from "./contexts/WorkspaceContext"

export default function App() {
  const navigate = useNavigate()

  useEffect(() => {
    const handleAuthRedirect = (e: CustomEvent) => {
      navigate(e.detail.path)
    }
    const handleAuthError = () => {
      navigate('/login', { replace: true })
    }
    window.addEventListener('auth:redirect', handleAuthRedirect as EventListener)
    window.addEventListener('elein-auth-error', handleAuthError)
    return () => {
      window.removeEventListener('auth:redirect', handleAuthRedirect as EventListener)
      window.removeEventListener('elein-auth-error', handleAuthError)
    }
  }, [navigate])

  return (
    <ThemeProvider defaultTheme="dark" storageKey="elein-ui-theme">
      <AuthProvider>
        <WorkspaceProvider>
          <Toaster theme="dark" position="bottom-right" />
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/accept-invite" element={<AcceptInvite />} />
          
          <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
            <Route path="/" element={<EleInCampaigns />} />
            <Route path="/chat" element={<ChatInterface />} />

            <Route path="/elein" element={<EleInDashboard />} />
            <Route path="/elein/accounts" element={<EleInAccounts />} />
            <Route path="/elein/leads" element={<EleInLeads />} />
            <Route path="/elein/campaigns" element={<EleInCampaigns />} />
            <Route path="/elein/campaigns/:id" element={<EleInCampaignDetail />} />
            <Route path="/elein/inbox" element={<EleInInbox />} />
            
            {/* New Premium Sidebar Routes */}
            <Route path="/elein/knowledge" element={<EleInKnowledge />} />
            <Route path="/elein/templates" element={<EleInTemplates />} />
            <Route path="/elein/admin" element={<EleInAdmin />} />
            <Route path="/elein/integrations" element={<EleInIntegrations />} />
            <Route path="/elein/settings" element={<EleInSettings />} />
            <Route path="/elein/agency" element={<EleInAgencySettings />} />
            <Route path="/elein/billing" element={<EleInBilling />} />
          </Route>
          <Route path="/elein/campaigns/new" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
          <Route path="/elein/welcome" element={<ProtectedRoute><EleInWelcome /></ProtectedRoute>} />
          
          {/* Public route: users must reach this even when their 403 MFA_REQUIRED gate is active */}
          <Route path="/mfa-setup" element={<MFASetupPage />} />

          {/* Catch-all redirect to avoid black screens on broken URLs */}
          <Route path="*" element={<Navigate to="/elein/campaigns" replace />} />
        </Routes>
        </WorkspaceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
