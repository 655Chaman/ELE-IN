import { useState, useEffect } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { 
  ChevronRight, ChevronLeft, Target, 
  Settings, User, Mail, Users, LayoutDashboard,
  BrainCircuit, Copy, Link as LinkIcon, Plug, CreditCard,
  CheckCircle, Globe, AlertTriangle
} from 'lucide-react';

import { ApiKeyModal } from './ApiKeyModal';
import { useKeys } from "@/hooks/useDashboard";
import { useAuth } from "@/lib/AuthContext";
import { useTheme } from './ThemeProvider';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { AnimatedThemeToggler } from './ui/animated-theme-toggler';

import { GlowingEffect } from './ui/glowing-effect';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { PauseOctagon, Building2, ChevronDown } from 'lucide-react';
export function AppLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeMarket, setActiveMarket] = useState("biotech");
  const [isModalOpen, setModalOpen] = useState(false);
  const [isWorkspaceDropdownOpen, setIsWorkspaceDropdownOpen] = useState(false);

  const { signOut } = useAuth();
  const { theme, setTheme } = useTheme();
  const { keys, saveKeys } = useKeys();
  const { workspaces, activeWorkspaceId, setActiveWorkspaceId, isPendingDeletion, myAgencies } = useWorkspace();
  const location = useLocation();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'x') {
        e.preventDefault();
        setIsSidebarOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const navCategories = [
    {
      title: "MAIN",
      items: [
        { label: 'Dashboard', icon: <LayoutDashboard size={14} strokeWidth={1.5} />, href: '/elein' },
        { label: 'Inbox', icon: <Mail size={14} strokeWidth={1.5} />, href: '/elein/inbox' },
        { label: 'Campaigns', icon: <Target size={14} strokeWidth={1.5} />, href: '/elein/campaigns' },
        { label: 'Leads', icon: <Users size={14} strokeWidth={1.5} />, href: '/elein/leads' },
        { label: 'Curation Review', icon: <CheckCircle size={14} strokeWidth={1.5} />, href: '/elein/admin' },
      ]
    },
    {
      title: "ASSETS",
      items: [
        { label: 'AI Knowledge', icon: <BrainCircuit size={14} strokeWidth={1.5} />, href: '/elein/knowledge' },
        { label: 'Templates', icon: <Copy size={14} strokeWidth={1.5} />, href: '/elein/templates' },
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
      {isPendingDeletion && (
        <div className="w-full bg-destructive/90 text-white text-sm font-semibold flex items-center justify-center gap-3 py-3 px-4 sticky top-0 z-50">
          <AlertTriangle size={18} className="shrink-0" />
          <span>
            This workspace is scheduled for deletion. All data mutations are disabled during the 14-day grace period.
            <a href="/elein/settings" className="underline ml-2 font-bold hover:opacity-80 transition-opacity">View Settings</a>
          </span>
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
              <div className="w-full flex justify-center cursor-pointer" onClick={() => setIsSidebarOpen(true)}>
                <img src="/logo-icon.png" alt="Ele-in" className="w-6 h-6 object-cover rounded-md" />
              </div>
            )}
            
            {isSidebarOpen && (
              <button 
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="p-1 text-sidebar-foreground/60 hover:text-sidebar-foreground transition-colors"
                title="Toggle Sidebar (Cmd+X)"
              >
                <ChevronLeft size={16} />
              </button>
            )}
          </div>

          {/* Workspace Switcher */}
          {isSidebarOpen ? (
            <div className="px-3 pt-4 pb-2">
              <div className="flex items-center justify-between px-1 mb-1.5">
                <p className="text-[9px] font-semibold text-sidebar-foreground/60 uppercase tracking-widest">
                  Current Workspace
                </p>
                {myAgencies && myAgencies.some(a => a.role === 'owner' || a.role === 'admin') && (
                  <button 
                    onClick={(e) => {
                      e.preventDefault();
                      window.location.href = '/elein/agency';
                    }}
                    className="text-sidebar-foreground/60 hover:text-primary transition-colors flex items-center gap-1 text-[9px] font-semibold uppercase tracking-widest"
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
                  <div className="fixed inset-0 z-40" onClick={() => setIsWorkspaceDropdownOpen(false)}></div>
                )}
                
                <button 
                  onClick={() => setIsWorkspaceDropdownOpen(!isWorkspaceDropdownOpen)}
                  className="w-full flex items-center justify-between p-2 rounded-xl hover:bg-sidebar-accent/40 transition-colors border border-transparent hover:border-sidebar-border/50 group relative z-50"
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    {(() => {
                      const activeWs = workspaces.find(w => w.id === activeWorkspaceId) || workspaces[0];
                      return (
                        <>
                          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center text-[11px] font-bold tracking-wider shrink-0 shadow-sm">
                            {activeWs?.name?.substring(0, 2).toUpperCase() || "WS"}
                          </div>
                          <div className="flex flex-col items-start truncate">
                            <span className="text-sm font-semibold text-sidebar-foreground truncate">{activeWs?.name || "Loading..."}</span>
                            <span className="text-[10px] text-sidebar-foreground/60 font-medium tracking-wide">
                              {activeWs?.account_count || 0} Connected Account{activeWs?.account_count !== 1 ? 's' : ''}
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                  <ChevronDown size={14} className={`text-sidebar-foreground/40 transition-transform duration-200 group-hover:text-sidebar-foreground/80 shrink-0 ${isWorkspaceDropdownOpen ? 'rotate-180' : ''}`} />
                </button>
                
                {isWorkspaceDropdownOpen && (
                  <div className="absolute z-50 w-[260px] left-0 mt-2 bg-popover border border-border rounded-xl shadow-xl overflow-hidden py-1 animate-in fade-in zoom-in-95 duration-100">
                    <div className="px-3 py-2 border-b border-border/50">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Switch Workspace</span>
                    </div>
                    <div className="max-h-[300px] overflow-y-auto custom-scrollbar p-1.5 space-y-0.5">
                      {workspaces.map(ws => (
                        <button
                          key={ws.id}
                          onClick={() => { 
                            setActiveWorkspaceId(ws.id);
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
            <div className="px-2 pt-4 pb-2 flex justify-center">
              {(() => {
                const activeWs = workspaces.find(w => w.id === activeWorkspaceId);
                const name = activeWs?.name || "WS";
                const initials = name.substring(0, 2).toUpperCase();
                return (
                  <button
                    onClick={() => setIsSidebarOpen(true)}
                    className="w-9 h-9 rounded-full bg-primary/10 border border-primary/20 text-primary flex items-center justify-center text-[11px] font-bold tracking-wider hover:bg-primary/20 transition-colors cursor-pointer shrink-0"
                    title={name}
                  >
                    {initials}
                  </button>
                );
              })()}
            </div>
          )}

          <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-6">
            {navCategories.map((category, idx) => (
              <div key={idx} className="space-y-1">
                {isSidebarOpen && (
                  <p className="px-3 text-[9px] font-semibold text-sidebar-foreground/60 uppercase tracking-widest mb-3">
                    {category.title}
                  </p>
                )}
                <div className="space-y-[1px]">
                  {category.items.map(item => {
                    const isActive = item.href ? ((item.href === '/' || item.href === '/elein') ? location.pathname === item.href : location.pathname.startsWith(item.href)) : false;
                    
                    const className = `w-full flex items-center gap-3 px-3 py-1.5 group relative rounded-lg ${
                      isActive 
                        ? 'text-sidebar-foreground'
                        : 'text-sidebar-foreground/60 hover:text-sidebar-foreground'
                    }`;

                    const innerContent = (
                      <>
                        {isActive && (
                          <>
                            <motion.div
                              layoutId="sidebar-active-pill"
                              className="absolute inset-0 rounded-lg bg-sidebar-accent/50"
                              transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
                            />
                            <GlowingEffect
                              spread={20}
                              glow={true}
                              disabled={false}
                              proximity={40}
                              inactiveZone={0.01}
                              borderWidth={1}
                              variant="white"
                            />
                          </>
                        )}
                        <div className={`shrink-0 relative z-10 ${isActive ? 'text-primary' : 'text-sidebar-foreground/60 group-hover:text-sidebar-foreground'} transition-colors`}>
                          {item.icon}
                        </div>
                        {isSidebarOpen && <span className="whitespace-nowrap text-[12px] font-medium relative z-10">{item.label}</span>}
                      </>
                    );

                    return item.onClick ? (
                      <button
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
              onClick={async () => {
                if (!window.confirm("PANIC PAUSE: Are you sure you want to pause ALL active campaigns immediately? This will stop all outgoing connections and messages.")) return;
                try {
                  const res = await fetchWithAuth("/api/elein/campaigns/pause-all", { method: "POST" });
                  if (!res.ok) throw new Error("Failed to pause");
                  toast.success("All active campaigns have been paused.");
                  // Optional: Refresh page to reflect new campaign states
                  setTimeout(() => window.location.reload(), 1000);
                } catch (e) {
                  toast.error("Failed to pause campaigns.");
                }
              }}
              className="w-full flex items-center gap-3 px-3 py-2 text-destructive-foreground bg-destructive hover:bg-destructive/90 rounded-lg transition-colors font-bold shadow-sm"
              title={!isSidebarOpen ? "Panic Pause All" : undefined}
            >
              <div className="shrink-0"><PauseOctagon size={14} strokeWidth={2.5} /></div>
              {isSidebarOpen && <span className="text-[12px]">Panic Pause All</span>}
            </button>
            <div className="w-full flex items-center justify-between px-2">
               {isSidebarOpen && <span className="text-[10px] uppercase font-semibold text-sidebar-foreground/60 tracking-widest">Theme</span>}
               <AnimatedThemeToggler variant="circle" theme={theme as any} onThemeChange={setTheme} />
            </div>
            <button 
              onClick={() => signOut()}
              className="w-full flex items-center gap-3 px-3 py-2 text-sidebar-foreground/60 hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              title={!isSidebarOpen ? "Sign Out" : undefined}
            >
              <div className="shrink-0"><User size={14} strokeWidth={1.5} /></div>
              {isSidebarOpen && <span className="text-[12px] font-medium">Sign Out</span>}
            </button>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto bg-background relative">
          <div className="relative h-full">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                className="h-full"
              >
                <Outlet context={{ activeMarket, setActiveMarket }} />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      <ApiKeyModal 
        isOpen={isModalOpen} 
        onClose={() => setModalOpen(false)} 
        onSave={saveKeys}
        initialKeys={keys}
      />
    </div>
  );
}
