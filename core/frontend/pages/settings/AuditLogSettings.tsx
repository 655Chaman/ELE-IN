import { useState, useMemo } from "react";
import { Activity, Clock, ShieldAlert, Users, User, Megaphone, AlertTriangle, ChevronDown, ChevronUp, Lock, SearchX, ServerCrash } from "lucide-react";
import useSWR from "swr";
import SpotlightCard from "@/components/SpotlightCard";
import { fetcher } from "@/lib/apiClient";
import { formatDistanceToNow } from "date-fns";
import { motion, AnimatePresence } from "motion/react";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

type Category = 'Security' | 'Team' | 'Account' | 'Campaign' | 'Deletion' | 'Other';

const getCategory = (action: string): Category => {
  if (action.includes('deletion_')) return 'Deletion';
  if (action.includes('2fa') || action === 'member.removed') return 'Security';
  if (action.startsWith('member.') || action.startsWith('workspace.invite_')) return 'Team';
  if (action.startsWith('account.')) return 'Account';
  if (action.startsWith('campaign.')) return 'Campaign';
  return 'Other';
};

const getCategoryStyles = (category: Category) => {
  switch (category) {
    case 'Security':
      return { icon: ShieldAlert, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' };
    case 'Team':
      return { icon: Users, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' };
    case 'Account':
      return { icon: User, color: 'text-primary/80', bg: 'bg-primary/10', border: 'border-primary/30' };
    case 'Campaign':
      return { icon: Megaphone, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' };
    case 'Deletion':
      return { icon: AlertTriangle, color: 'text-red-500', bg: 'bg-red-500/20', border: 'border-red-500/50 animate-pulse' };
    default:
      return { icon: Activity, color: 'text-muted-foreground', bg: 'bg-muted/10', border: 'border-border/50' };
  }
};

const parseAction = (entry: any) => {
  const targetId = entry.target_id ? entry.target_id.slice(0, 8) : 'unknown';
  const beforeState = entry.before_state || {};
  const afterState = entry.after_state || {};

  switch (entry.action) {
    case "workspace.invite_sent":
      return `Invited ${afterState.email || 'unknown'} as ${afterState.role || 'member'}`;
    case "member.role_changed":
      return `Changed ${targetId} role from ${beforeState.role || 'unknown'} to ${afterState.role || 'unknown'}`;
    case "member.removed":
      return `Removed ${targetId} from the workspace`;
    case "account.status_updated":
      return `Account ${targetId} status changed to ${afterState.status || 'unknown'}`;
    case "workspace.deletion_requested":
      return `Initiated 14-day workspace deletion sequence`;
    case "workspace.require_2fa_updated":
      return `2FA enforcement ${afterState.enabled ? 'enabled' : 'disabled'}`;
    case "campaign.created":
      return `Created campaign ${targetId}`;
    case "campaign.paused":
      return `Paused campaign ${targetId}`;
    default: {
      if (!entry.action || typeof entry.action !== 'string') return "Unknown action";
      const str = entry.action.replace(/\./g, ' ').replace(/_/g, ' ');
      return str.charAt(0).toUpperCase() + str.slice(1);
    }
  }
};

function LogEntryRow({ entry, isLatest }: { entry: any; isLatest: boolean }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const category = getCategory(entry.action);
  const styles = getCategoryStyles(category);
  const Icon = styles.icon;

  const actorLabel = entry.actor_id ? entry.actor_id.slice(0, 8) : 'system';

  return (
    <>
      <tr 
        className={`group hover:bg-muted/50 transition-colors cursor-pointer ${isLatest ? 'bg-primary/5' : ''}`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <td className="px-6 py-4 whitespace-nowrap">
          <div className="flex items-center gap-3">
            <div className={`p-1.5 rounded-md ${styles.bg} ${styles.color}`}>
              <Icon size={16} />
            </div>
            <div className="flex flex-col">
              <span className="font-medium text-sm text-foreground flex items-center gap-2">
                {parseAction(entry)}
                {isLatest && (
                  <span className="px-1.5 py-0.5 rounded-full bg-primary/20 text-primary text-[10px] font-bold uppercase tracking-wider">
                    Latest
                  </span>
                )}
              </span>
            </div>
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap">
          <span className="inline-flex items-center gap-1.5 font-mono bg-muted/50 px-2 py-1 rounded-md border border-border/50 text-xs">
            <User size={12} className="opacity-70" />
            {actorLabel}
          </span>
        </td>
        <td className="px-6 py-4 whitespace-nowrap">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock size={12} className="opacity-70" /> 
            {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
          </span>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-right">
          <button 
            className="p-1.5 rounded-lg text-muted-foreground group-hover:text-foreground transition-colors"
            aria-label="Toggle details"
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </td>
      </tr>
      
      <AnimatePresence>
        {isExpanded && (
          <tr>
            <td colSpan={4} className="p-0 border-b-0">
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden bg-muted/20"
              >
                <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs font-mono border-b border-border/50 shadow-inner">
                  {entry.before_state && Object.keys(entry.before_state).length > 0 && (
                    <div className="bg-background rounded-lg p-4 border border-border overflow-x-auto">
                      <div className="text-[10px] uppercase text-muted-foreground mb-3 font-semibold tracking-wider">Before</div>
                      <pre className="text-muted-foreground">{JSON.stringify(entry.before_state, null, 2)}</pre>
                    </div>
                  )}
                  {entry.after_state && Object.keys(entry.after_state).length > 0 && (
                    <div className="bg-background rounded-lg p-4 border border-border overflow-x-auto">
                      <div className="text-[10px] uppercase text-muted-foreground mb-3 font-semibold tracking-wider">After</div>
                      <pre className="text-foreground">{JSON.stringify(entry.after_state, null, 2)}</pre>
                    </div>
                  )}
                  {(!entry.before_state || Object.keys(entry.before_state).length === 0) && (!entry.after_state || Object.keys(entry.after_state).length === 0) && (
                    <div className="text-muted-foreground italic col-span-full py-2">No additional state details available.</div>
                  )}
                </div>
              </motion.div>
            </td>
          </tr>
        )}
      </AnimatePresence>
    </>
  );
}

export function AuditLogSettings({ workspaceId }: { workspaceId: string | null }) {
  const [filter, setFilter] = useState<Category | 'All'>('All');
  const [displayCount, setDisplayCount] = useState(20);
  
  const { data, isLoading, error } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/audit-log` : null,
    fetcher
  );

  const entries = data?.entries || [];

  const filteredEntries = useMemo(() => {
    return entries.filter((e: any) => filter === 'All' || getCategory(e.action) === filter);
  }, [entries, filter]);
  
  const displayedEntries = useMemo(() => {
    return filteredEntries.slice(0, displayCount);
  }, [filteredEntries, displayCount]);

  const hasMore = displayedEntries.length < filteredEntries.length;

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="Please select a workspace to view its audit trail." icon={Activity} />;
  }

  return (
    <div className="space-y-6">
      <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
        {/* Subtle Background Glow */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 relative z-10">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-primary/10 rounded-xl border border-primary/20 shadow-inner">
              <Activity className="text-primary" size={24} />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-2xl font-bold tracking-tight text-foreground">Audit Trail</h2>
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-muted/30 border border-border/50 text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
                  <Lock size={10} /> Read Only
                </div>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                Immutable, reverse-chronological record of all critical events.
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 bg-background/50 p-1 rounded-xl border border-border/50 self-start md:self-auto overflow-x-auto max-w-full">
            {(['All', 'Security', 'Team', 'Account', 'Campaign', 'Deletion', 'Other'] as const).map((f) => (
              <button
                key={f}
                onClick={() => {
                  setFilter(f);
                  setDisplayCount(20);
                }}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 whitespace-nowrap ${
                  filter === f 
                    ? 'bg-surface shadow-sm text-foreground border border-border/50' 
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/30 border border-transparent'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {error ? (
          <div className="flex flex-col items-center justify-center py-16 text-center border border-destructive/20 rounded-xl bg-destructive/5">
            <ServerCrash className="text-destructive mb-3" size={32} />
            <h3 className="text-base font-semibold text-destructive mb-1">Failed to load audit logs</h3>
            <p className="text-sm text-destructive/70">There was an error communicating with the server.</p>
          </div>
        ) : isLoading ? (
          <SettingsLoadingSkeleton />
        ) : filteredEntries.length === 0 ? (
          <EmptyState 
            title="No activity found" 
            description={filter === 'All' ? "No audit logs have been recorded in this workspace yet." : `No events matching the "${filter}" filter were found.`} 
            icon={SearchX} 
          />
        ) : (
          <div className="flex flex-col gap-6">
            <div className="w-full overflow-x-auto rounded-xl border border-border/50 bg-surface/50 shadow-sm relative">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-muted/50 sticky top-0 z-10 backdrop-blur-md border-b border-border/50">
                  <tr>
                    <th className="px-6 py-4 font-semibold tracking-wider">Event</th>
                    <th className="px-6 py-4 font-semibold tracking-wider">Actor</th>
                    <th className="px-6 py-4 font-semibold tracking-wider">Time</th>
                    <th className="px-6 py-4 font-semibold tracking-wider text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {displayedEntries.map((entry: any, i: number) => (
                    <LogEntryRow 
                      key={entry.id || i} 
                      entry={entry} 
                      isLatest={i === 0 && filter === 'All'} 
                    />
                  ))}
                </tbody>
              </table>
            </div>
            
            {hasMore && (
              <div className="flex justify-center mt-2">
                <button
                  onClick={() => setDisplayCount(prev => prev + 20)}
                  className="px-6 py-2.5 rounded-xl border border-border/50 bg-background hover:bg-muted/50 text-sm font-medium transition-colors shadow-sm flex items-center gap-2"
                >
                  Load More Activity
                </button>
              </div>
            )}
          </div>
        )}
      </SpotlightCard>
    </div>
  );
}
