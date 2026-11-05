import { useState, useEffect } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { 
  ChevronRight, ChevronLeft, Target, 
  Settings, User, Mail, Users, LayoutDashboard,
  BrainCircuit, Copy, Link as LinkIcon, Plug, CreditCard,
  CheckCircle, Globe, AlertTriangle, Shield, Share2, Sparkles, RefreshCw,
  Search
} from 'lucide-react';

import { ApiKeyModal } from './ApiKeyModal';
import { CommandPalette } from './CommandPalette';
import { useKeys } from "@/hooks/useDashboard";
import { useAuth } from "@/lib/AuthContext";
import { useTheme } from './ThemeProvider';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { AnimatedThemeToggler } from './ui/animated-theme-toggler';
import { OfflineBanner } from './OfflineBanner';

import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { PauseOctagon, Building2, ChevronDown } from 'lucide-react';
import { CreditBadge } from './billing/CreditBadge';
import { OnboardingChecklistWidget } from './onboarding/OnboardingChecklistWidget';
import { ElesiumLogo } from './ElesiumLogo';

export function AppLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [showPanicConfirm, setShowPanicConfirm] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const [activeMarket, setActiveMarket] = useState("biotech");
  const [isModalOpen, setModalOpen] = useState(false);
  const [isWorkspaceDropdownOpen, setIsWorkspaceDropdownOpen] = useState(false);

  const navigate = useNavigate();
  const { signOut, user } = useAuth();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { keys, saveKeys } = useKeys();
  const { workspaces, activeWorkspaceId, activeWorkspaceTier, isFree, isPro, isEnterprise, setActiveWorkspaceId, isPendingDeletion, myAgencies, refreshWorkspaces } = useWorkspace();
  const [isRestoringWorkspace, setIsRestoringWorkspace] = useState(false);
  const location = useLocation();

  const handleCancelDeletion = async () => {
    if (!activeWorkspaceId) return;
    setIsRestoringWorkspace(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${activeWorkspaceId}/cancel-deletion`, {
        method: 'POST'
      });
      if (!res.ok) {
        const errPayload = await res.json().catch(() => null);
        throw new Error(errPayload?.detail || 'Failed to cancel workspace deletion');
      }
      await refreshWorkspaces();
      toast.success('Workspace deletion cancelled! All data mutations are now active.');
    } catch (e: any) {
      toast.error(e?.message || 'Could not cancel deletion.');
    } finally {
      setIsRestoringWorkspace(false);
    }
  };

  const userRole = (user?.app_metadata?.role || user?.user_metadata?.role || '').toLowerCase();
  const isUserAdmin = userRole === 'admin' || userRole === 'superadmin' || user?.user_metadata?.is_admin === true;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Guard against typing in text inputs, textareas, contenteditable, or ARIA textboxes
      const target = e.target as HTMLElement | null;
      if (
        target && (
          target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable ||
          target.getAttribute('role') === 'textbox'
        )
      ) {
        return;
      }

      // Sidebar toggle shortcut: Cmd+B / Ctrl+B or Cmd+\ (VS Code / Linear convention; never hijacks Cmd+X Cut)
      if ((e.metaKey || e.ctrlKey) && (e.key.toLowerCase() === 'b' || e.key === '\\')) {
        e.preventDefault();
        setIsSidebarOpen(prev => !prev);
      }
      if (e.key === 'Escape' && isWorkspaceDropdownOpen) {
        setIsWorkspaceDropdownOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isWorkspaceDropdownOpen]);

  const navCategories = [
    {
      title: "MAIN",
      items: [
        { label: 'Dashboard', icon: <LayoutDashboard size={14} strokeWidth={1.5} />, href: '/elein' },
        { label: 'Inbox', icon: <Mail size={14} strokeWidth={1.5} />, href: '/elein/inbox' },
        { label: 'Campaigns', icon: <Target size={14} strokeWidth={1.5} />, href: '/elein/campaigns' },
        { label: 'Leads', icon: <Users size={14} strokeWidth={1.5} />, href: '/elein/leads' },
        ...(isUserAdmin ? [{ label: 'Admin', icon: <Shield size={14} strokeWidth={1.5} />, href: '/elein/admin' }] : []),
      ]
    },
    {
      title: "ASSETS",
      items: [
        { label: 'Elesium Knowledge', icon: <ElesiumLogo size={14} />, href: '/elein/knowledge' },
        { label: 'Templates', icon: <Copy size={14} strokeWidth={1.5} />, href: '/elein/templates' },
        { label: 'Engagement & Content', icon: <Share2 size={14} strokeWidth={1.5} />, href: '/elein/engagement' },
        { label: 'Elesium Growth Tools', icon: <ElesiumLogo size={14} />, href: '/elein/campaigns?tools=true' },
      ]
    },
    {
      title: "INFRASTRUCTURE",
      items: [
        { label: 'Linked Accounts', icon: <LinkIcon size={14} strokeWidth={1.5} />, href: '/elein/accounts' },
        { label: 'Integrations', icon: <Plug size={14} strokeWidth={1.5} />, href: '/elein/integrations' },
      ]
    },
    {
      title: "WORKSPACE",
      items: [
        { label: 'Settings', icon: <Settings size={14} strokeWidth={1.5} />, href: '/elein/settings' },
        { label: 'Billing', icon: <CreditCard size={14} strokeWidth={1.5} />, href: '/elein/billing' },
        { label: 'API & Webhooks', icon: <Plug size={14} strokeWidth={1.5} />, onClick: () => setModalOpen(true) },
      ]
    }
  ];

  return (
    <div className="h-[100dvh] bg-background text-foreground flex flex-col overflow-hidden text-sm font-sans selection:bg-primary/30">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-lg focus:shadow-2xl focus:font-semibold focus:outline-none focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>
      <OfflineBanner />
      {isEnterprise && (
        <div className="w-full bg-slate-950/95 border-b border-emerald-500/20 text-slate-200 text-xs px-4 py-1.5 flex items-center justify-between gap-4 font-mono tracking-tight shrink-0 z-40 backdrop-blur-md">
          <div className="flex items-center gap-3 overflow-x-auto no-scrollbar">
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold uppercase text-[10px] tracking-wider shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Enterprise VIP Telemetry
            </div>
            <div className="hidden sm:flex items-center gap-1.5 text-muted-foreground text-[11px] shrink-0">
              <span className="text-slate-400">PROXY POOL:</span>
              <span className="text-emerald-400 font-semibold">DEDICATED RESIDENTIAL (100% HEALTH)</span>
            </div>
            <div className="hidden md:flex items-center gap-1.5 text-muted-foreground text-[11px] shrink-0">
              <span className="text-slate-400">SENDER PODS:</span>
              <span className="text-emerald-400 font-semibold">AFFINITY LOCKED</span>
            </div>
            <div className="hidden lg:flex items-center gap-1.5 text-muted-foreground text-[11px] shrink-0">
              <span className="text-slate-400">DISPATCH CONCURRENCY:</span>
              <span className="text-emerald-400 font-semibold">UNLIMITED WORKERS</span>
            </div>
            <div className="hidden xl:flex items-center gap-1.5 text-muted-foreground text-[11px] shrink-0">
              <span className="text-slate-400">DNS SENTRY:</span>
              <span className="text-emerald-400 font-semibold">RFC 8058 ALIGNED</span>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Link
              to="/elein/accounts"
              className="text-[11px] text-emerald-400 hover:text-emerald-300 hover:underline flex items-center gap-1 transition-colors"
            >
              <span>Manage Pods</span>
              <ChevronRight size={11} />
            </Link>
          </div>
        </div>
      )}
      {isPendingDeletion && (
        <div className="w-full bg-destructive/95 text-white text-xs font-semibold flex items-center justify-between gap-3 py-2.5 px-4 sticky top-0 z-50 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="shrink-0 animate-pulse text-white" />
            <span>
              This workspace is scheduled for statutory deletion (14-day grace period). All data mutations are locked.
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleCancelDeletion}
              disabled={isRestoringWorkspace}
              className="px-3 py-1 rounded bg-white text-destructive hover:bg-white/90 font-bold transition-all shadow-xs cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshCw size={11} className={isRestoringWorkspace ? "animate-spin" : ""} />
              <span>{isRestoringWorkspace ? "Restoring..." : "Cancel Deletion & Restore"}</span>
            </button>
            <Link to="/elein/settings" className="underline hover:opacity-80 transition-opacity text-xs ml-1 font-medium">
              View Settings
            </Link>
          </div>
        </div>
      )}
      <div className="flex-1 flex overflow-hidden">
        {/* Global Left Sidebar */}
        <aside className={`flex flex-col border-r border-sidebar-border bg-sidebar transition-all duration-300 ease-in-out shrink-0 z-20 ${isSidebarOpen ? 'w-[240px]' : 'w-16'}`}>
          
          {/* Brand Header */}
          <div className="h-[60px] flex items-center justify-between px-4 border-b border-sidebar-border shrink-0">
            {isSidebarOpen ? (
              <div className="flex items-center gap-2 font-semibold text-[13px] tracking-widest uppercase text-sidebar-foreground">
                <img src="/logo-icon.png" alt="Ele-in" className="w-6 h-6 object-cover rounded-md" />
                ELE-IN
              </div>
            ) : (
              <button 
                type="button" 
                aria-label="Expand sidebar" 
                className="w-full flex justify-center cursor-pointer" 
                onClick={() => setIsSidebarOpen(true)}
              >
                <img src="/logo-icon.png" alt="Ele-in" className="w-6 h-6 object-cover rounded-md" />
              </button>
            )}
            
            {isSidebarOpen && (
              <button 
                type="button"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="p-1 text-sidebar-foreground/75 hover:text-sidebar-foreground transition-colors"
                title="Toggle Sidebar (Cmd+B)"
                aria-label="Collapse sidebar"
              >
                <ChevronLeft size={16} />
              </button>
            )}
          </div>

          {/* Workspace Switcher */}
          {isSidebarOpen ? (
            <div className="px-3 pt-4 pb-2">
              <div className="flex items-center justify-between px-1 mb-1.5">
                <p className="text-[9px] font-semibold text-sidebar-foreground/80 uppercase tracking-widest">
                  Current Workspace
                </p>
                {myAgencies && myAgencies.some(a => a.role === 'owner' || a.role === 'admin') && (
                  <button 
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate('/elein/agency');
                    }}
                    className="text-sidebar-foreground/80 hover:text-primary transition-colors flex items-center gap-1 text-[9px] font-semibold uppercase tracking-widest"
                    title="Agency Management"
                  >
                    <Building2 size={10} />
                    Agency
                  </button>
                )}
              </div>

              <div className="relative w-full" id="workspace-dropdown-container">
                {/* Invisible backdrop for closing when clicking outside */}
                {isWorkspaceDropdownOpen && (
                  <div 
                    className="fixed inset-0 z-40" 
                    onClick={() => setIsWorkspaceDropdownOpen(false)}
                    role="presentation"
                    aria-hidden="true"
                  />
                )}
                
                <button 
                  type="button"
                  onClick={() => setIsWorkspaceDropdownOpen(!isWorkspaceDropdownOpen)}
                  aria-expanded={isWorkspaceDropdownOpen}
                  aria-haspopup="listbox"
                  aria-label="Switch workspace"
                  className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-sidebar-accent/40 transition-colors border border-transparent hover:border-sidebar-border/50 group relative z-50"
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    {(() => {
                      const activeWs = workspaces.find(w => w.id === activeWorkspaceId) || workspaces[0];
                      const wsTier = (activeWs?.tier || activeWorkspaceTier || 'FREE').toUpperCase();
                      const isEnt = wsTier === 'ENTERPRISE' || Boolean(activeWs?.is_platform_owner);
                      const isAg = wsTier === 'AGENCY';
                      const isPr = wsTier === 'PRO' || wsTier === 'GROWTH';
                      return (
                        <>
                          <div className={`w-8 h-8 rounded-md flex items-center justify-center text-[11px] font-bold tracking-wider shrink-0 shadow-sm ${
                            isEnt ? 'bg-purple-500/15 border border-purple-500/30 text-purple-400' :
                            isAg ? 'bg-indigo-500/15 border border-indigo-500/30 text-indigo-400' :
                            isPr ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400' :
                            'bg-primary/10 border border-primary/20 text-primary'
                          }`}>
                            {activeWs?.name?.substring(0, 2).toUpperCase() || "WS"}
                          </div>
                          <div className="flex flex-col items-start truncate min-w-0">
                            <div className="flex items-center gap-1.5 truncate max-w-full">
                              <span className="text-sm font-semibold text-sidebar-foreground truncate">{activeWs?.name || "Loading..."}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[8px] font-black uppercase tracking-wider shrink-0 border ${
                                isEnt ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' :
                                isAg ? 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30' :
                                isPr ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
                                'bg-muted text-muted-foreground border-border/60'
                              }`}>
                                {isEnt ? 'Enterprise VIP' : isAg ? 'Agency Hub' : isPr ? 'Growth Pro' : 'Free Tier'}
                              </span>
                            </div>
                            <span className="text-[10px] text-sidebar-foreground/80 font-medium tracking-wide">
                              {activeWs?.account_count || 0} Connected Account{activeWs?.account_count !== 1 ? 's' : ''}
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                  <ChevronDown size={14} className={`text-sidebar-foreground/70 transition-transform duration-200 group-hover:text-sidebar-foreground shrink-0 ${isWorkspaceDropdownOpen ? 'rotate-180' : ''}`} />
                </button>
                
                {isWorkspaceDropdownOpen && (
                  <div className="absolute z-50 w-[260px] left-0 mt-2 bg-popover border border-border rounded-lg shadow-xl overflow-hidden py-1 animate-in fade-in zoom-in-95 duration-100">
                    <div className="px-3 py-2 border-b border-border/50">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Switch Workspace</span>
                    </div>
                    <div className="max-h-[300px] overflow-y-auto custom-scrollbar p-1.5 space-y-0.5">
                      {workspaces.map(ws => (
                        <button
                          type="button"
                          key={ws.id}
                          onClick={() => { 
                            if (ws.id !== activeWorkspaceId) {
                              toast.loading(`Switching to ${ws.name}...`, { duration: 1500 });
                              setActiveWorkspaceId(ws.id);
                            }
                            setIsWorkspaceDropdownOpen(false);
                          }}
                          className={`w-full flex items-center gap-3 p-2 rounded-lg text-left transition-all ${ws.id === activeWorkspaceId ? 'bg-primary/10' : 'hover:bg-muted'}`}
                        >
                          <div className={`w-8 h-8 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 ${ws.id === activeWorkspaceId ? 'bg-primary text-primary-foreground shadow-sm' : 'bg-muted-foreground/10 text-muted-foreground'}`}>
                            {ws.name.substring(0, 2).toUpperCase()}
                          </div>
                          <div className="flex flex-col truncate">
                            <span className={`text-sm truncate ${ws.id === activeWorkspaceId ? 'font-bold text-foreground' : 'font-medium text-foreground/80'}`}>{ws.name}</span>
                            <span className="text-[10px] text-muted-foreground">{ws.account_count} account{ws.account_count !== 1 ? 's' : ''}</span>
                          </div>
                          {ws.id === activeWorkspaceId && (
                             <div className="ml-auto shrink-0 text-primary">
                               <CheckCircle size={14} strokeWidth={2.5} />
                             </div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="px-3 pt-4 pb-2 flex justify-center">
              {(() => {
                const activeWs = workspaces.find(w => w.id === activeWorkspaceId);
                const name = activeWs?.name || "WS";
                const initials = name.substring(0, 2).toUpperCase();
                return (
                  <button
                    type="button"
                    onClick={() => setIsSidebarOpen(true)}
                    className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center text-[11px] font-bold tracking-wider hover:bg-primary/20 transition-colors cursor-pointer shrink-0"
                    title={name}
                    aria-label={`Current workspace: ${name}. Click to expand sidebar.`}
                  >
                    {initials}
                  </button>
                );
              })()}
            </div>
          )}

          <CreditBadge workspaceId={activeWorkspaceId || ''} isSidebarOpen={isSidebarOpen} />
          
          {/* Quick Search & Command Palette Trigger (Cmd+K) */}
          <div className="px-3 py-1">
            {isSidebarOpen ? (
              <button
                type="button"
                onClick={() => {
                  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
                }}
                className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-sidebar-accent/30 hover:bg-sidebar-accent/60 border border-sidebar-border/40 text-sidebar-foreground/80 hover:text-sidebar-foreground transition-all text-xs cursor-pointer group shadow-2xs"
                title="Search or execute actions (⌘K)"
              >
                <div className="flex items-center gap-2">
                  <Search size={13} className="text-sidebar-foreground/75 group-hover:text-sidebar-foreground transition-colors" />
                  <span className="text-[11px] font-medium">Quick search...</span>
                </div>
                <kbd className="text-[9px] font-mono font-bold bg-sidebar-border/40 px-1.5 py-0.5 rounded text-sidebar-foreground/80 border border-sidebar-border/60">
                  ⌘K
                </kbd>
              </button>
            ) : (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => {
                    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
                  }}
                  className="size-8 rounded-lg hover:bg-sidebar-accent/50 text-sidebar-foreground/80 hover:text-sidebar-foreground flex items-center justify-center transition-colors cursor-pointer border border-transparent hover:border-sidebar-border/50"
                  title="Quick search (⌘K)"
                  aria-label="Quick search (⌘K)"
                >
                  <Search size={14} />
                </button>
              </div>
            )}
          </div>

          <nav className="flex-1 overflow-y-auto py-2 px-3 space-y-5">
            {navCategories.map((category, idx) => (
              <div key={idx} className="space-y-1">
                {isSidebarOpen && (
                  <p className="px-3 text-[9px] font-semibold text-sidebar-foreground/80 uppercase tracking-widest mb-3">
                    {category.title}
                  </p>
                )}
                <div className="space-y-[1px]">
                  {category.items.map(item => {
                    const normalizedPath = location.pathname.replace(/\/$/, '') || '/';
                const isActive = item.href ? ((item.href === '/' || item.href === '/elein') ? normalizedPath === item.href : normalizedPath.startsWith(item.href)) : false;
                    
                    const className = `w-full flex items-center gap-3 px-3 py-1.5 group relative rounded-lg ${
                      isActive 
                        ? 'text-sidebar-foreground'
                        : 'text-sidebar-foreground/80 hover:text-sidebar-foreground'
                    }`;

                    const innerContent = (
                      <>
                        {isActive && (
                          <motion.div
                            layoutId="sidebar-active-pill"
                            className="absolute inset-0 rounded-lg bg-sidebar-accent border border-sidebar-border/60"
                            transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
                          />
                        )}
                        <div className={`shrink-0 relative z-10 ${isActive ? 'text-primary' : 'text-sidebar-foreground/80 group-hover:text-sidebar-foreground'} transition-colors`}>
                          {item.icon}
                        </div>
                        {isSidebarOpen && <span className="whitespace-nowrap text-[12px] font-medium relative z-10">{item.label}</span>}
                      </>
                    );

                    return item.onClick ? (
                      <button
                        type="button"
                        key={item.label}
                        onClick={item.onClick}
                        className={className}
                        title={!isSidebarOpen ? item.label : undefined}
                      >
                        {innerContent}
                      </button>
                    ) : (
                      <Link
                        key={item.label}
                        to={item.href!}
                        className={className}
                        title={!isSidebarOpen ? item.label : undefined}
                      >
                        {innerContent}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
            

          </nav>

          {/* User Profile */}
          <div className="p-3 border-t border-sidebar-border shrink-0 space-y-2">
            <button 
              type="button"
              onClick={() => setShowPanicConfirm(true)}
              className="w-full flex items-center gap-3 px-3 py-2 text-destructive-foreground bg-destructive hover:bg-destructive/90 rounded-lg transition-colors font-bold shadow-sm cursor-pointer"
              title={!isSidebarOpen ? "Panic Pause All" : undefined}
            >
              <div className="shrink-0"><PauseOctagon size={14} strokeWidth={2.5} /></div>
              {isSidebarOpen && <span className="text-[12px]">Panic Pause All</span>}
            </button>
            <div className={`w-full flex items-center ${isSidebarOpen ? 'justify-between px-3' : 'justify-center'}`}>
               {isSidebarOpen && <span className="text-[10px] uppercase font-semibold text-sidebar-foreground/80 tracking-widest">Theme</span>}
               <AnimatedThemeToggler variant="circle" theme={resolvedTheme} onThemeChange={setTheme} />
            </div>
            
            <Link 
              to="/mfa-setup"
              className="w-full flex items-center gap-3 px-3 py-2 text-sidebar-foreground/80 hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
              title={!isSidebarOpen ? "Personal Security (2FA)" : undefined}
            >
              <div className="shrink-0"><Shield size={14} strokeWidth={1.5} /></div>
              {isSidebarOpen && <span className="text-[12px] font-medium">Personal Security</span>}
            </Link>

            <button 
              type="button"
              onClick={() => signOut()}
              className="w-full flex items-center gap-3 px-3 py-2 text-sidebar-foreground/80 hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              title={!isSidebarOpen ? "Sign Out" : undefined}
            >
              <div className="shrink-0"><User size={14} strokeWidth={1.5} /></div>
              {isSidebarOpen && <span className="text-[12px] font-medium">Sign Out</span>}
            </button>
          </div>
        </aside>

        {/* Main Content Area */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto overflow-x-clip bg-background relative focus:outline-none">
          <Outlet context={{ activeMarket, setActiveMarket }} />
        </main>
      </div>

      <CommandPalette />
      <OnboardingChecklistWidget />

      <ApiKeyModal 
        isOpen={isModalOpen} 
        onClose={() => setModalOpen(false)} 
        onSave={saveKeys}
        initialKeys={keys}
      />

      {/* Panic Pause Confirmation Modal */}
      {showPanicConfirm && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md"
          onClick={() => { if (!isPausing) setShowPanicConfirm(false); }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="panic-dialog-title"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-md overflow-hidden rounded-2xl border border-destructive/30 bg-card p-6 shadow-2xl backdrop-blur-xl"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-destructive/15 border border-destructive/30 text-destructive">
                <PauseOctagon size={24} strokeWidth={2.5} />
              </div>
              <div className="space-y-1.5 flex-1">
                <h3 id="panic-dialog-title" className="text-base font-bold text-foreground">
                  Panic Pause All Campaigns?
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  This will immediately halt all active outreach sequences, pending message dispatches, and connection requests across all accounts in this workspace.
                </p>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-border/40">
              <button
                type="button"
                onClick={() => setShowPanicConfirm(false)}
                disabled={isPausing}
                className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground rounded-lg border border-border hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
              >
                Keep Running
              </button>
              <button
                type="button"
                disabled={isPausing}
                onClick={async () => {
                  setIsPausing(true);
                  try {
                    const res = await fetchWithAuth("/api/elein/campaigns/pause-all", { method: "POST" });
                    if (!res.ok) throw new Error("Failed to pause");
                    toast.success("All active campaigns have been paused.");
                    setShowPanicConfirm(false);
                    window.dispatchEvent(new CustomEvent("campaigns:refresh"));
                  } catch (e) {
                    toast.error("Failed to pause campaigns.");
                  } finally {
                    setIsPausing(false);
                  }
                }}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold text-destructive-foreground bg-destructive hover:bg-destructive/90 rounded-lg transition-colors cursor-pointer shadow-xs disabled:opacity-50"
              >
                {isPausing ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                    <span>Pausing Fleet...</span>
                  </>
                ) : (
                  <>
                    <PauseOctagon size={14} />
                    <span>Pause All Campaigns</span>
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
