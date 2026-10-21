import { Routes, Route, useNavigate, Navigate } from "react-router-dom"
import { Toaster } from "sonner"
import { useEffect, lazy, Suspense } from "react"
import { AppLayout } from "./components/AppLayout"
import { ThemeProvider } from "./components/ThemeProvider"
import { AuthProvider, useAuth } from "./lib/AuthContext"
import { WorkspaceProvider } from "./contexts/WorkspaceContext"
import { PaywallProvider } from "./contexts/PaywallContext"

// Lazy-loaded route components for high-performance code splitting
const Login = lazy(() => import("@admin/Login").then(m => ({ default: m.Login })))
const AcceptInvite = lazy(() => import("@admin/AcceptInvite").then(m => ({ default: m.AcceptInvite })))
const MFASetupPage = lazy(() => import("@admin/MFASetupPage").then(m => ({ default: m.MFASetupPage })))
const OnboardingWizard = lazy(() => import("./pages/onboarding/OnboardingWizard").then(m => ({ default: m.OnboardingWizard })))

const ChatInterface = lazy(() => import("./core/layout/ChatInterface").then(m => ({ default: m.ChatInterface })))
const EleInDashboard = lazy(() => import("@dashboard/EleInDashboard").then(m => ({ default: m.EleInDashboard })))
const EleInAccounts = lazy(() => import("@accounts/EleInAccounts").then(m => ({ default: m.EleInAccounts })))
const EleInLeads = lazy(() => import("@leads/EleInLeads").then(m => ({ default: m.EleInLeads })))
const EleInCampaigns = lazy(() => import("@campaigns/EleInCampaigns").then(m => ({ default: m.EleInCampaigns })))
const EleInCreateCampaign = lazy(() => import("@campaigns/EleInCreateCampaign").then(m => ({ default: m.default || m.EleInCreateCampaign })))
const EleInCampaignDetail = lazy(() => import("@campaigns/EleInCampaignDetail").then(m => ({ default: m.EleInCampaignDetail })))
const EleInInbox = lazy(() => import("@inbox/EleInInbox").then(m => ({ default: m.EleInInbox })))
const EleInTemplates = lazy(() => import("./core/layout/EleInTemplates").then(m => ({ default: m.EleInTemplates })))
const EleInKnowledge = lazy(() => import("@knowledge/EleInKnowledge"))
const EleInEngagementStudio = lazy(() => import("./components/engagement/EleInEngagementStudio").then(m => ({ default: m.EleInEngagementStudio })))
const EleInAdmin = lazy(() => import("@admin/EleInAdmin").then(m => ({ default: m.EleInAdmin })))
const EleInIntegrations = lazy(() => import("@integrations/EleInIntegrations").then(m => ({ default: m.EleInIntegrations })))
const EleInSettings = lazy(() => import("@admin/EleInSettings").then(m => ({ default: m.EleInSettings })))
const EleInAgencySettings = lazy(() => import("@admin/EleInAgencySettings").then(m => ({ default: m.EleInAgencySettings })))
const EleInBilling = lazy(() => import("@admin/EleInBilling").then(m => ({ default: m.EleInBilling })))

function RouteLoadingFallback() {
  return (
    <div className="flex-1 min-h-[50vh] flex items-center justify-center p-8 text-muted-foreground">
      <div className="flex flex-col items-center gap-3">
        <div className="size-6 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        <span className="text-xs font-medium text-muted-foreground">Loading workspace view...</span>
      </div>
    </div>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();
  
  if (isLoading) {
    return <div className="min-h-screen bg-background flex items-center justify-center text-muted-foreground">Loading...</div>;
  }
  
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
}

function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background text-foreground p-4">
      <div className="w-16 h-16 rounded-xl bg-muted/40 border border-border flex items-center justify-center mb-6">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground"><circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/></svg>
      </div>
      <h1 className="text-2xl font-bold mb-2">Page not found</h1>
      <p className="text-muted-foreground mb-8">The page you're looking for doesn't exist.</p>
      <button type="button" onClick={() => navigate('/elein')} className="px-6 py-2.5 rounded-lg bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors">Back to Dashboard</button>
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
            <Suspense fallback={<RouteLoadingFallback />}>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/accept-invite" element={<AcceptInvite />} />
                
                <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
                  <Route path="/" element={<Navigate to="/elein" replace />} />
                  <Route path="/dashboard" element={<Navigate to="/elein" replace />} />
                  <Route path="/elein/dashboard" element={<Navigate to="/elein" replace />} />
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
            </Suspense>
          </PaywallProvider>
        </WorkspaceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
