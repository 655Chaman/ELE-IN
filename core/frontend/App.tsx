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
import { EleInEngagementStudio } from "./components/engagement/EleInEngagementStudio"
import { EleInWelcome } from "@admin/EleInWelcome"
import { OnboardingWizard } from "./pages/onboarding/OnboardingWizard"
 
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
import { PaywallProvider } from "./contexts/PaywallContext"

function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background text-foreground p-4">
      <div className="w-16 h-16 rounded-2xl bg-muted/40 border border-border flex items-center justify-center mb-6">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground"><circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/></svg>
      </div>
      <h1 className="text-2xl font-bold mb-2">Page not found</h1>
      <p className="text-muted-foreground mb-8">The page you're looking for doesn't exist.</p>
      <button onClick={() => navigate('/elein/campaigns')} className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors">Back to Campaigns</button>
    </div>
  );
}

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
          <PaywallProvider>
            <Toaster theme="dark" position="bottom-right" />
            <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/accept-invite" element={<AcceptInvite />} />
            
            <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
              <Route path="/" element={<Navigate to="/elein/campaigns" replace />} />
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
              <Route path="/elein/engagement" element={<EleInEngagementStudio />} />
              <Route path="/elein/content-studio" element={<Navigate to="/elein/engagement" replace />} />
              <Route path="/elein/admin" element={<EleInAdmin />} />
              <Route path="/elein/integrations" element={<EleInIntegrations />} />
              <Route path="/elein/settings" element={<EleInSettings />} />
              <Route path="/elein/agency" element={<EleInAgencySettings />} />
              <Route path="/elein/billing" element={<EleInBilling />} />
            </Route>
            <Route path="/elein/campaigns/new" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
            <Route path="/campaigns/new" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
            <Route path="/elein/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
            <Route path="/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
            <Route path="/onboarding" element={<ProtectedRoute><OnboardingWizard /></ProtectedRoute>} />
            <Route path="/elein/welcome" element={<ProtectedRoute><OnboardingWizard /></ProtectedRoute>} />
            
            {/* Public route: users must reach this even when their 403 MFA_REQUIRED gate is active */}
            <Route path="/mfa-setup" element={<MFASetupPage />} />

            {/* Catch-all route to display helpful 404 page */}
            <Route path="*" element={<NotFound />} />
            </Routes>
          </PaywallProvider>
        </WorkspaceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
