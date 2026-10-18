import { useState, useMemo } from 'react';
import useSWR, { mutate } from 'swr';
import { 
  Search, Plus, Paperclip, Mic, Sparkles, MessageSquare, PanelLeftClose, PanelLeftOpen, Home, ChevronRight, Check, Copy
} from 'lucide-react';
import { toast } from 'sonner';
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { friendlyToast } from '../../components/FriendlyError';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import { CustomSelect } from '@/components/ui/select';
import { useAuth } from '@/lib/AuthContext';
import { useWorkspace } from '@/contexts/WorkspaceContext';

const API_BASE = "/api/elein/inbox";

interface Lead {
  id: string;
  company_name: string;
  kdm_first: string;
  job_title: string;
  company_description: string;
  status: string;
  market?: string;
  last_message?: string;
}

interface HistoryRecord {
  id: string;
  prospect_message: string;
  ai_draft: string;
  channel: string;
  objection_type: string;
  created_at: string;
}

const DEFAULT_DEMO_LEADS: Lead[] = [
  {
    id: "lead-apex",
    company_name: "Apex Logistics",
    kdm_first: "Marcus",
    job_title: "Head of Fleet Operations",
    company_description: "Mid-market freight brokerage looking to automate dispatch and reduce broker manual messaging time.",
    status: "NEW_REPLY",
    market: "Logistics",
    last_message: "Can you send over pricing and how this connects with our current TMS?"
  },
  {
    id: "lead-finpulse",
    company_name: "FinPulse Labs",
    kdm_first: "Elena",
    job_title: "VP of Product",
    company_description: "Series B fintech scaling recurring payments infrastructure and cross-border settlement rails.",
    status: "OBJECTION_RAISED",
    market: "Fintech",
    last_message: "We're currently locked into a contract with Stripe until Q3. Not sure the timing is right."
  }
];

export function ChatInterface() {
  const { user } = useAuth();
  const { workspaces, activeWorkspaceId } = useWorkspace();
  const currentWorkspaceName = workspaces.find(w => w.id === activeWorkspaceId)?.name || 'Agency';
  const currentUserName = user?.user_metadata?.first_name || user?.user_metadata?.name || user?.email?.split('@')[0] || 'Ryan';

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Fetch real inbox threads from the backend
  const { data: threadsData, mutate: mutateThreads } = useSWR<any[]>(
    '/api/elein/inbox/threads',
    fetcher,
    { fallbackData: [] }
  );

  const leads: Lead[] = useMemo(() => {
    if (Array.isArray(threadsData) && threadsData.length > 0) {
      return threadsData.map((t: any, idx: number) => ({
        id: t.lead_id || t.thread_key || `thread-${idx}`,
        company_name: t.company || t.sender_name || 'Prospect Company',
        kdm_first: t.sender_name?.split(' ')[0] || 'Prospect',
        job_title: t.title || 'Decision Maker',
        company_description: t.last_message ? `Last inquiry: "${t.last_message}"` : 'Active prospect thread',
        status: t.deal_stage || 'NEW_REPLY',
        market: t.market || 'Outbound',
        last_message: t.last_message
      }));
    }
    return DEFAULT_DEMO_LEADS;
  }, [threadsData]);

  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [localHistory, setLocalHistory] = useState<Record<string, HistoryRecord[]>>({});

  const [inputText, setInputText] = useState("");
  const [isDrafting, setIsDrafting] = useState(false);
  const [channel, setChannel] = useState("email");
  const [objectionType, setObjectionType] = useState("none");

  const safeLeads = Array.isArray(leads) ? leads : [];
  const filteredLeads = safeLeads.filter(lead => 
    (lead.company_name || '').toLowerCase().includes(searchQuery.toLowerCase()) || 
    (lead.kdm_first || '').toLowerCase().includes(searchQuery.toLowerCase())
  );
  
  const selectedLead = safeLeads.find(l => l.id === selectedLeadId);

  // SWR for messages of the active thread
  const { data: serverThreadMessages } = useSWR<any[]>(
    selectedLead ? `/api/elein/inbox/threads/${encodeURIComponent(selectedLead.kdm_first)}?lead_id=${encodeURIComponent(selectedLead.id || 'unknown')}` : null,
    fetcher,
    { fallbackData: [] }
  );

  const activeHistory: HistoryRecord[] = useMemo(() => {
    if (!selectedLead) return [];
    const local = localHistory[selectedLead.id] || [];
    const serverRecords: HistoryRecord[] = (Array.isArray(serverThreadMessages) ? serverThreadMessages : [])
      .map((m: any) => ({
        id: m.id || Math.random().toString(36).substring(7),
        prospect_message: m.direction === 'inbound' ? m.message_text : '',
        ai_draft: m.direction === 'outbound' ? m.message_text : '',
        channel: 'email',
        objection_type: 'none',
        created_at: m.created_at || new Date().toISOString()
      }))
      .filter(r => r.prospect_message || r.ai_draft);

    return [...serverRecords, ...local];
  }, [selectedLead, serverThreadMessages, localHistory]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Draft copied to clipboard!");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDraftReply = async () => {
    if (!selectedLead || !inputText.trim()) return;
    setIsDrafting(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/ai-suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sender_name: currentUserName,
          thread_messages: [{
            message_text: inputText,
            direction: "inbound"
          }],
          intent: objectionType,
          lead_profile: {
            company_name: selectedLead.company_name,
            kdm_first: selectedLead.kdm_first,
            job_title: selectedLead.job_title,
            company_description: selectedLead.company_description
          },
          campaign_context: ""
        })
      });

      if (!res.ok) throw new Error("Failed to get AI suggestion");

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let draftText = "";
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          draftText += decoder.decode(value);
        }
      }

      const newRecord: HistoryRecord = {
        id: Math.random().toString(36).substring(7),
        prospect_message: inputText,
        ai_draft: draftText || "Thanks for reaching out! Let me know when this week works best for a quick walk-through.",
        channel: channel,
        objection_type: objectionType,
        created_at: new Date().toISOString()
      };
      
      setLocalHistory(prev => ({
        ...prev,
        [selectedLead.id]: [...(prev[selectedLead.id] || []), newRecord]
      }));
      setInputText("");
      mutate('/api/elein/billing/credits/balance');
      mutate('/api/elein/workspaces/billing');
      mutate((key: any) => typeof key === 'string' && (key.startsWith('/api/elein/billing/credits/balance') || key.startsWith('/api/elein/billing') || key.startsWith('/api/elein/workspaces/billing')), undefined, { revalidate: true });
      toast.success("AI reply draft generated!");
    } catch (err: any) {
      friendlyToast('Message drafting failed — please try again.', err);
    } finally {
      setIsDrafting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleDraftReply();
    }
  };

  return (
    <div className="flex w-full h-full text-sm">
      {/* Middle Column: Chat History & Threads Sidebar */}
      <div className={`${isSidebarOpen ? 'w-[280px]' : 'w-0 overflow-hidden border-none'} bg-sidebar border-r border-border/60 flex flex-col shrink-0 transition-all duration-200`}>
        <div className="h-[60px] flex items-center justify-between px-4 border-b border-border/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center border border-border/60">
              <MessageSquare size={16} className="text-muted-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-foreground truncate max-w-[150px]">{currentUserName}</span>
              <span className="text-[11px] text-muted-foreground">Conversations ({filteredLeads.length})</span>
            </div>
          </div>
          <button 
            type="button" 
            onClick={() => setIsSidebarOpen(false)}
            aria-label="Collapse panel" 
            className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted/40 transition-colors cursor-pointer"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>

        <div className="p-4 space-y-4 shrink-0">
          <button 
            type="button"
            onClick={() => { setSelectedLeadId(null); setInputText(""); }}
            className="w-full flex items-center justify-center gap-2 py-2 bg-muted/40 hover:bg-muted border border-border/60 rounded-lg text-foreground font-medium transition-colors cursor-pointer shadow-xs"
          >
            <Plus size={16} />
            <span>New chat</span>
          </button>

          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search conversations..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-background border border-border/60 rounded-lg py-1.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-4">
          {filteredLeads.map(lead => (
            <button 
              key={lead.id}
              type="button"
              onClick={() => setSelectedLeadId(lead.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors cursor-pointer ${
                selectedLeadId === lead.id 
                  ? 'bg-muted text-foreground font-medium shadow-xs' 
                  : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
              }`}
            >
              <MessageSquare size={14} className="shrink-0" />
              <div className="flex flex-col truncate w-full">
                <span className="truncate">{lead.company_name || 'Unknown Company'}</span>
                {lead.kdm_first && (
                  <span className={`text-[10px] ${selectedLeadId === lead.id ? 'text-muted-foreground font-medium' : 'text-muted-foreground/80'} truncate`}>
                    {lead.kdm_first} • {lead.job_title}
                  </span>
                )}
              </div>
            </button>
          ))}
          {filteredLeads.length === 0 && (
             <div className="text-center text-xs text-muted-foreground py-4">No active conversations found.</div>
          )}
        </div>
      </div>

      {/* Right Column: Chat & AI Drafting Canvas */}
      <div className="flex-1 bg-background flex flex-col relative overflow-hidden">
        {selectedLead ? (
          <>
            {/* Header */}
            <div className="h-[60px] border-b border-border/60 flex items-center justify-between px-6 sm:px-8 shrink-0 bg-background/80 backdrop-blur-sm sticky top-0 z-10">
              <div className="flex items-center gap-2">
                {!isSidebarOpen && (
                  <button
                    type="button"
                    onClick={() => setIsSidebarOpen(true)}
                    aria-label="Open sidebar"
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors mr-1 cursor-pointer"
                    title="Open conversations sidebar"
                  >
                    <PanelLeftOpen size={16} />
                  </button>
                )}
                <span className="font-semibold text-[15px] text-foreground truncate max-w-[260px] sm:max-w-md">
                  Drafting Reply for {selectedLead.company_name}
                </span>
              </div>
              <div className="flex items-center gap-2 sm:gap-3">
                  <CustomSelect
                    value={channel}
                    onValueChange={setChannel}
                    size="sm"
                    className="w-24 sm:w-28"
                    triggerClassName="bg-card border-border text-xs rounded-lg px-2.5 sm:px-3 py-1.5 h-8 text-foreground"
                    options={[
                      { value: "email", label: "Email" },
                      { value: "linkedin", label: "LinkedIn" },
                    ]}
                  />
                  <CustomSelect
                    value={objectionType}
                    onValueChange={setObjectionType}
                    size="sm"
                    className="w-32 sm:w-36"
                    triggerClassName="bg-card border-border text-xs rounded-lg px-2.5 sm:px-3 py-1.5 h-8 text-foreground"
                    options={[
                      { value: "none", label: "No Objection" },
                      { value: "timing", label: "Timing" },
                      { value: "competitor", label: "Competitor" },
                      { value: "price", label: "Price" },
                      { value: "not_interested", label: "Not Interested" },
                    ]}
                  />
              </div>
            </div>
            
            {/* Breadcrumbs */}
            <div className="px-6 sm:px-8 py-3 flex items-center justify-between gap-2 text-xs text-muted-foreground border-b border-border/40 shrink-0">
              <div className="flex items-center gap-2 truncate">
                <Home size={12} className="shrink-0" />
                <ChevronRight size={12} className="shrink-0" />
                <span className="truncate">{currentWorkspaceName}</span>
                <ChevronRight size={12} className="shrink-0" />
                <span className="text-foreground font-medium truncate">{currentUserName}</span>
                <ChevronRight size={12} className="shrink-0" />
                <span className="text-foreground truncate">{selectedLead.kdm_first || 'Prospect'}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                 <span className="px-2 py-0.5 rounded-full bg-muted border border-border/60 uppercase text-[9px] text-muted-foreground font-medium">
                   {selectedLead.status?.replace('_', ' ') || 'ACTIVE'}
                 </span>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto px-6 sm:px-8 py-6">
              <div className="max-w-[800px] mx-auto space-y-6">
                
                {/* Context Bubble (System) */}
                <div className="flex flex-col items-center">
                  <div className="text-[11px] font-semibold text-muted-foreground mb-1.5 uppercase tracking-wider">
                    Prospect Intelligence Profile
                  </div>
                  <div className="bg-card border border-border/60 rounded-xl p-4 max-w-full text-muted-foreground text-xs leading-relaxed w-full shadow-xs">
                    <p className="font-bold text-foreground mb-1">
                      {selectedLead.company_name} • {selectedLead.kdm_first} ({selectedLead.job_title})
                    </p>
                    <p>{selectedLead.company_description || 'Active prospect thread loaded.'}</p>
                  </div>
                </div>

                {/* Conversation History & Draft Bubbles */}
                {activeHistory.length === 0 ? (
                  <div className="p-8 text-center border border-dashed border-border/60 rounded-xl bg-muted/10 space-y-2">
                    <MessageSquare size={24} className="mx-auto text-muted-foreground/50" />
                    <p className="text-xs text-muted-foreground">
                      No replies logged yet for this lead. Paste the prospect's email or message below to draft an objection-handling reply.
                    </p>
                  </div>
                ) : (
                  activeHistory.map((msg) => (
                    <div key={msg.id} className="space-y-4">
                      {/* Prospect Inbound Message */}
                      {msg.prospect_message && (
                        <div className="flex justify-end">
                          <div className="bg-muted/80 border border-border text-foreground px-4 py-3 rounded-xl max-w-[85%] whitespace-pre-wrap leading-relaxed shadow-xs text-xs">
                            {msg.prospect_message}
                          </div>
                        </div>
                      )}

                      {/* AI Draft Outbound Message */}
                      {msg.ai_draft && (
                        <div className="flex justify-start items-start gap-3">
                          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20 shrink-0 mt-0.5 text-primary">
                            <ElesiumLogo size={14} />
                          </div>
                          <div className="flex flex-col items-start max-w-[85%] relative group">
                            <div className="bg-card border border-border/60 text-foreground px-4 py-3 rounded-xl whitespace-pre-wrap leading-relaxed shadow-xs text-xs">
                              {msg.ai_draft}
                            </div>
                            <div className="flex items-center gap-2 mt-2">
                              <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-md border border-border/60 uppercase font-mono">
                                {msg.channel}
                              </span>
                              {msg.objection_type && msg.objection_type !== 'none' && (
                                <span className="text-[10px] text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-md border border-border/60 uppercase font-mono">
                                  Obj: {msg.objection_type}
                                </span>
                              )}
                              <button 
                                type="button"
                                onClick={() => handleCopy(msg.id, msg.ai_draft)}
                                className="text-[10px] text-muted-foreground bg-muted hover:bg-muted/80 hover:text-foreground px-2 py-0.5 rounded-md border border-border/60 uppercase transition-colors opacity-100 sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100 flex items-center gap-1 cursor-pointer"
                              >
                                {copiedId === msg.id ? (
                                  <>
                                    <Check size={10} className="text-emerald-500" />
                                    <span className="text-emerald-500 font-semibold">Copied!</span>
                                  </>
                                ) : (
                                  <>
                                    <Copy size={10} />
                                    <span>Copy Draft</span>
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Input & Action Area */}
            <div className="p-4 sm:p-6 shrink-0 bg-gradient-to-t from-background via-background to-transparent pt-6 border-t border-border/30">
              <div className="max-w-[800px] mx-auto relative">
                <div className="relative flex items-end bg-card border border-border rounded-xl p-2.5 pl-3.5 shadow-sm focus-within:border-primary/50 transition-colors gap-2">
                  <button 
                    type="button" 
                    aria-label="Attach context file" 
                    onClick={() => toast.info("Document context attachments can also be configured via Knowledge Base.")}
                    className="text-muted-foreground hover:text-foreground p-1 mb-0.5 shrink-0 transition-colors cursor-pointer"
                    title="Attach context file"
                  >
                    <Paperclip size={16} />
                  </button>

                  <textarea 
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isDrafting}
                    rows={2}
                    placeholder="Paste prospect's message here (Press Enter to draft, Shift+Enter for new line)..." 
                    className="flex-1 bg-transparent border-none text-foreground focus:outline-none placeholder:text-muted-foreground py-1 resize-none text-xs leading-relaxed max-h-32 disabled:opacity-50"
                  />

                  <button 
                    type="button" 
                    aria-label="Voice input" 
                    onClick={() => toast.info("Voice dictation supported via your system voice input shortcut.")}
                    className="text-muted-foreground hover:text-foreground p-1 mb-0.5 shrink-0 transition-colors cursor-pointer"
                    title="Voice input"
                  >
                    <Mic size={16} />
                  </button>

                  <button 
                    type="button"
                    onClick={handleDraftReply}
                    disabled={!inputText.trim() || isDrafting}
                    className="h-8 px-3 shrink-0 rounded-lg bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground flex items-center gap-1.5 text-primary-foreground font-semibold text-xs transition-colors shadow-xs cursor-pointer disabled:cursor-not-allowed mb-0.5"
                    aria-label="Generate AI Reply"
                  >
                    {isDrafting ? (
                      <div className="w-3.5 h-3.5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                    ) : (
                      <>
                        <Sparkles size={13} />
                        <span className="hidden sm:inline">Draft Reply</span>
                      </>
                    )}
                  </button>
                </div>
                <div className="mt-2 text-center text-[10px] text-muted-foreground">
                  {currentUserName} will analyze prospect context and craft a high-converting reply based on the selected channel and objection strategy.
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground relative p-8">
            <div className="w-16 h-16 rounded-xl bg-card border border-border/60 flex items-center justify-center mb-4 z-10 relative shadow-sm">
              <MessageSquare size={24} className="text-primary" />
            </div>
            <h4 className="text-sm font-bold text-foreground mb-1">Select a Conversation</h4>
            <p className="text-xs text-muted-foreground max-w-sm text-center leading-relaxed">
              Choose a lead from the sidebar to inspect previous interactions, handle objections, and generate contextual AI drafts.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
