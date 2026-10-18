import React from 'react';
import useSWR from 'swr';
import { Coins, Loader2, Plus } from 'lucide-react';
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
  const { data, isLoading } = useSWR(
    workspaceId ? '/api/elein/billing/credits/balance' : null, 
    () => fetcher('/api/elein/billing/credits/balance')
  );

  if (!workspaceId) return null;

  const balance = data?.balance ?? 0;
  const isLow = balance < 50;

  if (!isSidebarOpen) {
    return (
      <div className="px-2 pb-2 flex justify-center">
        <button 
          type="button"
          onClick={() => openTopUp()}
          className="w-9 h-9 rounded-lg bg-sidebar-accent/30 hover:bg-sidebar-accent/70 border border-sidebar-border/60 hover:border-sidebar-border text-sidebar-foreground flex items-center justify-center transition-all duration-150 cursor-pointer shrink-0 group relative"
          title={`${balance.toLocaleString()} Credits — Click to top up`}
          aria-label={`Credits: ${balance.toLocaleString()} available. Click to top up.`}
        >
          <Coins size={14} className={isLow ? "text-amber-500" : "text-emerald-500/90"} />
        </button>
      </div>
    );
  }

  return (
    <div className="px-3 pb-2">
      <button 
        type="button"
        onClick={() => openTopUp()}
        className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-sidebar-accent/25 hover:bg-sidebar-accent/60 border border-sidebar-border/50 hover:border-sidebar-border/80 transition-all duration-150 cursor-pointer text-left group"
        aria-label={`Workspace credits: ${balance.toLocaleString()} available. Click to top up.`}
        title="Workspace Credits — Click to top up"
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className={`w-5 h-5 rounded-md flex items-center justify-center shrink-0 border transition-colors ${
            isLow 
              ? "bg-amber-500/10 border-amber-500/20 text-amber-500" 
              : "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
          }`}>
            <Coins size={11} strokeWidth={2} />
          </div>
          <span className="text-[11px] font-medium text-sidebar-foreground/80 group-hover:text-sidebar-foreground transition-colors truncate">
            Credits
          </span>
        </div>
        
        <div className="flex items-center gap-1.5 shrink-0 pl-2">
          {isLoading ? (
            <Loader2 size={11} className="animate-spin text-muted-foreground/60" />
          ) : (
            <>
              <span className="text-[11px] font-semibold font-mono text-foreground tracking-tight">
                {balance.toLocaleString()}
              </span>
              <div className="w-3.5 h-3.5 rounded-full bg-sidebar-accent/60 group-hover:bg-primary group-hover:text-primary-foreground text-muted-foreground/70 flex items-center justify-center transition-colors">
                <Plus size={8} strokeWidth={2.5} />
              </div>
            </>
          )}
        </div>
      </button>
    </div>
  );
}
