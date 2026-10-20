import React, { useState } from 'react';
import useSWR from 'swr';
import { 
  Send, X, ShieldCheck, AlertCircle, Sparkles, Loader2, 
  Layers, CheckCircle2, Lock, Check, UserCheck, Flame
} from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'motion/react';
import { fetchWithAuth } from '@/lib/apiClient';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { CustomSelect } from '@/components/ui/select';
import { leadKeys } from './leadKeys';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface EnrollListInCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  listId?: string;
  listName?: string;
  leadIds?: string[];
  onSuccess?: (stats: { enrolled: number; skipped: number; collisions?: number }) => void;
}

export function EnrollListInCampaignModal({
  isOpen,
  onClose,
  listId,
  listName,
  leadIds,
  onSuccess,
}: EnrollListInCampaignModalProps) {
  const { activeWorkspaceId } = useWorkspace();
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>('');
  const [excludeOtherCampaigns, setExcludeOtherCampaigns] = useState<boolean>(true);
  const [excludeListId, setExcludeListId] = useState<string>('');
  const [isEnrolling, setIsEnrolling] = useState<boolean>(false);

  // Fetch campaigns in workspace via canonical leadKeys
  const campaignsKey = leadKeys.campaigns(activeWorkspaceId);
  const { data: rawCampaigns, isLoading: loadingCampaigns } = useSWR(isOpen ? campaignsKey : null, fetcher);

  // Fetch all lead lists for optional exclusion list selection via canonical leadKeys
  const listsKey = leadKeys.lists(activeWorkspaceId);
  const { data: rawLists } = useSWR(isOpen ? listsKey : null, fetcher);

  const campaigns: any[] = Array.isArray(rawCampaigns) 
    ? rawCampaigns.filter(c => c.status !== 'ARCHIVED' && c.status !== 'DELETED')
    : [];

  const availableLists: any[] = Array.isArray(rawLists) 
    ? rawLists.filter(l => l.id !== listId)
    : [];

  const isSelectedLeads = Boolean(leadIds && leadIds.length > 0);
  const leadCountText = isSelectedLeads 
    ? `${leadIds?.length} selected lead${leadIds?.length !== 1 ? 's' : ''}`
    : `all leads in "${listName || 'this list'}"`;

  const handleEnroll = async () => {
    if (!selectedCampaignId) {
      toast.error('Please select an outreach campaign first.');
      return;
    }

    setIsEnrolling(true);
    try {
      let res: any;
      if (isSelectedLeads && leadIds) {
        const response = await fetchWithAuth(`/api/elein/campaigns/${encodeURIComponent(selectedCampaignId)}/enroll`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            opportunity_ids: leadIds,
            excludeOtherCampaigns,
            excludeListId: excludeListId || undefined,
          }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || 'Failed to enroll leads in campaign');
        }
        res = await response.json();
      } else if (listId) {
        const response = await fetchWithAuth(`/api/elein/campaigns/${encodeURIComponent(selectedCampaignId)}/enroll_list`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            list_id: listId,
            excludeOtherCampaigns,
            excludeListId: excludeListId || undefined,
          }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || 'Failed to enroll list in campaign');
        }
        res = await response.json();
      } else {
        throw new Error('No target list or leads specified for enrollment.');
      }

      const enrolled = res.enrolled || 0;
      const skipped = res.skipped || 0;
      const collisions = res.collisions || 0;

      toast.success(
        `Successfully enrolled ${enrolled} lead${enrolled !== 1 ? 's' : ''}! ${
          skipped > 0 ? `(${skipped} skipped, ${collisions} collisions prevented)` : ''
        }`.trim()
      );

      if (onSuccess) {
        onSuccess({ enrolled, skipped, collisions });
      }
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'An error occurred during campaign enrollment. Please try again.');
    } finally {
      setIsEnrolling(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-background/80 backdrop-blur-md overflow-hidden animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isEnrolling) {
          onClose();
        }
      }}
    >
      <motion.div 
        role="dialog"
        aria-modal="true"
        aria-labelledby="enroll-campaign-modal-title"
        initial={{ opacity: 0, scale: 0.98, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 10 }}
        className="w-full max-w-lg bg-card border border-border/80 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90dvh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-5 border-b border-border/60 flex items-center justify-between bg-muted/20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-400 shadow-xs">
              <Send size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="enroll-campaign-modal-title" className="text-base font-bold text-foreground">
                  Enroll in Outreach Campaign
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                  Live Dispatch
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Dispatch {leadCountText} into an automated sequence.
              </p>
            </div>
          </div>

          <button 
            type="button"
            onClick={onClose}
            disabled={isEnrolling}
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto">
          {/* Campaign Selector */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground flex items-center justify-between">
              <span>Target Campaign</span>
              {loadingCampaigns && <span className="text-[11px] text-muted-foreground font-normal">Loading campaigns...</span>}
            </label>
            <CustomSelect
              value={selectedCampaignId}
              onValueChange={setSelectedCampaignId}
              disabled={isEnrolling || loadingCampaigns}
              placeholder="— Choose Campaign Sequence —"
              className="w-full"
              triggerClassName="text-xs font-semibold bg-background border-border/80 h-10"
              options={[
                { value: "", label: "— Choose Campaign Sequence —" },
                ...campaigns.map(camp => ({
                  value: camp.id,
                  label: `${camp.name} (${camp.status || 'DRAFT'})`,
                })),
              ]}
            />
            {campaigns.length === 0 && !loadingCampaigns && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 flex items-center gap-1.5 mt-1">
                <AlertCircle size={12} />
                No campaigns found. Please create a campaign first before enrolling leads.
              </p>
            )}
          </div>

          {/* CollisionGuard & Safety Options */}
          <div className="p-4 rounded-xl bg-muted/20 border border-border/70 space-y-3.5 shadow-xs">
            <div className="flex items-start gap-3">
              <label className="relative inline-flex items-center cursor-pointer mt-0.5 shrink-0">
                <input
                  type="checkbox"
                  checked={excludeOtherCampaigns}
                  onChange={(e) => setExcludeOtherCampaigns(e.target.checked)}
                  disabled={isEnrolling}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-muted peer-focus-visible:ring-2 peer-focus-visible:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
              <div>
                <div className="flex items-center gap-1.5">
                  <ShieldCheck size={14} className="text-emerald-600 dark:text-emerald-400" />
                  <span className="text-xs font-bold text-foreground">CollisionGuard™ Active</span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                  Automatically skip prospects currently in-flight in other campaigns to eliminate embarrassing duplicate messages.
                </p>
              </div>
            </div>

            {/* Optional Exclusion List */}
            {availableLists.length > 0 && (
              <div className="pt-3 border-t border-border/40 space-y-1.5">
                <label className="text-[11px] font-semibold text-muted-foreground">
                  Optional: Exclude Leads from Another List
                </label>
                <CustomSelect
                  value={excludeListId}
                  onValueChange={setExcludeListId}
                  disabled={isEnrolling}
                  size="sm"
                  placeholder="— None (Do not exclude another list) —"
                  className="w-full"
                  triggerClassName="text-xs bg-background border-border/80"
                  options={[
                    { value: "", label: "— None (Do not exclude another list) —" },
                    ...availableLists.map(l => ({
                      value: l.id,
                      label: `${l.name} (${l.row_count >= 0 ? `${l.row_count} leads` : 'List'})`,
                    })),
                  ]}
                />
              </div>
            )}
          </div>

          {/* DNC Notice */}
          <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs">
            <CheckCircle2 size={14} className="shrink-0" />
            <span>Do Not Contact (DNC) suppression rules will be evaluated automatically before enrollment.</span>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border/60 flex items-center justify-end gap-3 bg-muted/10 shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={isEnrolling}
            className="px-4 py-2 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleEnroll}
            disabled={isEnrolling || !selectedCampaignId}
            className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all flex items-center gap-2 shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isEnrolling ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                <span>Enrolling Leads...</span>
              </>
            ) : (
              <>
                <Send size={14} />
                <span>Enroll Leads</span>
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
