import { useState, useEffect } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
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

export function AppLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeMarket, setActiveMarket] = useState("biotech");
  const [isModalOpen, setModalOpen] = useState(false);

  const { signOut } = useAuth();
  const { theme, setTheme } = useTheme();
  const { keys, saveKeys } = useKeys();
  const { workspaces, activeWorkspaceId, setActiveWorkspaceId, isPendingDeletion } = useWorkspace();
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
        <aside className={`flex flex-col border-r border-border bg-background transition-all duration-300 ease-in-out shrink-0 z-20 ${isSidebarOpen ? 'w-[240px]' : 'w-16'}`}>
          
          {/* Brand Header */}
          <div className="h-[60px] flex items-center justify-between px-4 border-b border-border shrink-0">
            {isSidebarOpen ? (
              <div className="flex items-center gap-2 font-semibold text-[13px] tracking-widest uppercase text-foreground">
                ELE-IN
              </div>
            ) : (
              <div className="w-full flex justify-center text-foreground font-bold tracking-widest text-[10px]">ELE</div>
            )}
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-1 text-muted-foreground hover:text-foreground transition-colors"
              title="Toggle Sidebar (Cmd+X)"
            >
              {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
          </div>

          {/* Workspace Switcher */}
          {isSidebarOpen ? (
            <div className="px-3 pt-4 pb-2">
              <p className="px-1 text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-1.5">
                Current Workspace
              </p>
              <select 
                className="w-full bg-accent/30 border border-border rounded-md text-xs px-2 py-1.5 text-foreground outline-none focus:border-primary/50 cursor-pointer"
                value={activeWorkspaceId || ""}
                onChange={(e) => setActiveWorkspaceId(e.target.value)}
              >
                {workspaces.length === 0 ? (
                  <option value="" disabled>Loading workspace...</option>
                ) : (
                  workspaces.map(ws => (
                    <option key={ws.id} value={ws.id}>
                      {ws.name} ({ws.account_count} accounts)
                    </option>
                  ))
                )}
              </select>
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
                  <p className="px-3 text-[9px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">
                    {category.title}
                  </p>
                )}
                <div className="space-y-[1px]">
                  {category.items.map(item => {
                    const isActive = item.href ? ((item.href === '/' || item.href === '/elein') ? location.pathname === item.href : location.pathname.startsWith(item.href)) : false;
                    
                    const className = `w-full flex items-center gap-3 px-3 py-1.5 transition-colors group relative rounded-lg ${
                      isActive 
                        ? 'bg-accent/50 text-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent/30'
                    }`;

                    const innerContent = (
                      <>
                        {isActive && (
                          <GlowingEffect
                            spread={20}
                            glow={true}
                            disabled={false}
                            proximity={40}
                            inactiveZone={0.01}
                            borderWidth={1}
                            variant="white"
                          />
                        )}
                        <div className={`shrink-0 ${isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'}`}>
                          {item.icon}
                        </div>
                        {isSidebarOpen && <span className="whitespace-nowrap text-[12px] font-medium">{item.label}</span>}
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
          <div className="p-3 border-t border-border shrink-0 space-y-2">
            <div className="w-full flex items-center justify-between px-2">
               {isSidebarOpen && <span className="text-[10px] uppercase font-semibold text-muted-foreground tracking-widest">Theme</span>}
               <AnimatedThemeToggler variant="circle" theme={theme as any} onThemeChange={setTheme} />
            </div>
            <button 
              onClick={() => signOut()}
              className="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
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
            <Outlet context={{ activeMarket, setActiveMarket }} />
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
