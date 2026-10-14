import React from 'react';
import useSWR from 'swr';
import { Coins, Loader2 } from 'lucide-react';
import { fetcher } from '../../lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';

interface CreditBadgeProps {
  workspaceId: string;
  isSidebarOpen: boolean;
}

export function CreditBadge({ workspaceId, isSidebarOpen }: CreditBadgeProps) {
  const { openTopUp } = usePaywall();
  // Paranoia Layer 0 & 1: Canonical SWR key matching app-wide mutate calls in PaywallContext & CreditTopUpModal.
  // WorkspaceContext invalidates all caches on workspace change, ensuring zero stale cross-workspace leakage.
  const { data, error, isLoading } = useSWR(
    workspaceId ? '/api/elein/billing/credits/balance' : null, 
    () => fetcher('/api/elein/billing/credits/balance')
  );

  if (!workspaceId) return null;

  if (!isSidebarOpen) {
    return (
      <div className="px-2 pt-2 flex justify-center">
        <button 
          onClick={() => openTopUp()}
          className="w-9 h-9 rounded-full bg-primary/10 border border-primary/20 text-primary flex items-center justify-center hover:bg-primary/20 transition-colors group cursor-pointer shrink-0"
          title={`${data?.balance?.toLocaleString() ?? 0} Credits — Click to top up`}
        >
          <Coins size={14} className="group-hover:rotate-12 transition-transform" />
        </button>
      </div>
    );
  }

  return (
    <div className="px-4 pb-2">
        <div 
          onClick={() => openTopUp()}
          className="relative group w-full bg-sidebar-accent/20 hover:bg-sidebar-accent/50 border border-sidebar-border/60 hover:border-primary/30 rounded-xl overflow-hidden cursor-pointer transition-all duration-300"
        >
        <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
        
        <div className="p-2.5 flex items-center justify-between relative z-10">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-xl bg-background shadow-sm border border-border/50 text-primary group-hover:scale-110 transition-transform">
              <Coins size={14} className="group-hover:rotate-12 transition-transform" />
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-sidebar-foreground/60 uppercase tracking-widest leading-none mb-1">
                Workspace
              </span>
              <span className="text-xs font-semibold text-sidebar-foreground leading-none">
                Credits
              </span>
            </div>
          </div>
          
          <div className="flex items-center justify-end">
            {isLoading ? (
              <Loader2 size={12} className="animate-spin text-primary/50" />
            ) : (
              <span className="text-sm font-bold text-foreground font-mono tracking-tight bg-background/50 px-2 py-0.5 rounded-lg border border-border/30">
                {data?.balance?.toLocaleString() ?? 0}
              </span>
            )}
          </div>
        </div>
        
        <div className="h-[2px] w-full bg-sidebar-border/30 absolute bottom-0 left-0">
          <div className="h-full bg-gradient-to-r from-primary/40 to-primary group-hover:from-primary/80 group-hover:to-primary transition-colors duration-500" style={{ width: '100%' }} />
        </div>
      </div>
    </div>
  );
}
