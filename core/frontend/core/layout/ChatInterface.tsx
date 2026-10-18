import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState } from 'react';
import useSWR, { mutate } from 'swr';
import { 
  Search, Plus, Paperclip, Mic, ArrowUp, MessageSquare, PanelLeftClose, Home, ChevronRight, Check
} from 'lucide-react';
import { toast } from 'sonner';
import { friendlyToast } from '../../components/FriendlyError';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import { CustomSelect } from '@/components/ui/select';

const API_BASE = "/api/elein/inbox";
;

interface Lead {
  id: string;
  company_name: string;
  kdm_first: string;
  job_title: string;
  company_description: string;
  status: string;
  market: string;
}

interface HistoryRecord {
  id: string;
  prospect_message: string;
  ai_draft: string;
  channel: string;
  objection_type: string;
  created_at: string;
}

export function ChatInterface() {
  const { data: leads } = useSWR<Lead[]>(null, fetcher, { fallbackData: [] });
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  
  const { data: history, mutate: mutateHistory } = useSWR<HistoryRecord[]>(
    null,
    fetcher,
    { fallbackData: [] }
  );

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
  const safeHistory = Array.isArray(history) ? history : [];

  const handleDraftReply = async () => {
    if (!selectedLead || !inputText.trim()) return;
    setIsDrafting(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/ai-suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sender_name: "Ryan",
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

      const newRecord = {
        id: Math.random().toString(36).substring(7),
        prospect_message: inputText,
        ai_draft: draftText,
        channel: channel,
        objection_type: objectionType,
        created_at: new Date().toISOString()
      };
      
      mutateHistory((prev) => [...(prev || []), newRecord], false);
      setInputText("");
      mutate('/api/elein/billing/credits/balance');
      mutate('/api/elein/workspaces/billing');
      mutate((key: any) => typeof key === 'string' && (key.startsWith('/api/elein/billing/credits/balance') || key.startsWith('/api/elein/billing') || key.startsWith('/api/elein/workspaces/billing')), undefined, { revalidate: true });
      toast.success("AI response drafted!");
    } catch (err: any) {
      friendlyToast('Message send failed — please try again.', err);
    } finally {
      setIsDrafting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleDraftReply();
    }
  };

  return (
    <div className="flex w-full h-full text-sm">
      {/* Middle Column: Chat History */}
      <div className="w-[280px] bg-sidebar border-r border-border/60 flex flex-col shrink-0">
        <div className="h-[60px] flex items-center justify-between px-4 border-b border-border/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center border border-border/60">
              <MessageSquare size={16} className="text-muted-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-foreground">Ryan</span>
              <span className="text-[11px] text-muted-foreground">History ({safeLeads.length})</span>
            </div>
          </div>
          <button type="button" aria-label="Collapse panel" className="text-muted-foreground hover:text-foreground transition-colors">
            <PanelLeftClose size={16} />
          </button>
        </div>

        <div className="p-4 space-y-4 shrink-0">
          <button 
            type="button"
            onClick={() => { setSelectedLeadId(null); setInputText(""); }}
            className="w-full flex items-center justify-center gap-2 py-2 bg-muted/40 hover:bg-muted border border-border/60 rounded-lg text-foreground font-medium transition-colors"
          >
            <Plus size={16} />
            <span>New chat</span>
          </button>

          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search leads..." 
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
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                selectedLeadId === lead.id 
                  ? 'bg-muted text-foreground font-medium' 
                  : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
              }`}
            >
              <MessageSquare size={14} className="shrink-0" />
              <div className="flex flex-col truncate w-full">
                <span className="truncate">{lead.company_name || 'Unknown Company'}</span>
                {lead.kdm_first && (
                  <span className={`text-[10px] ${selectedLeadId === lead.id ? 'text-muted-foreground' : 'text-muted-foreground/80'} truncate`}>
                    {lead.kdm_first} • {lead.job_title}
                  </span>
                )}
              </div>
            </button>
          ))}
          {filteredLeads.length === 0 && (
             <div className="text-center text-xs text-muted-foreground py-4">No active leads found.</div>
          )}
        </div>
      </div>

      {/* Right Column: Chat Area */}
      <div className="flex-1 bg-background flex flex-col relative overflow-hidden">
        {selectedLead ? (
          <>
            {/* Header */}
            <div className="h-[60px] border-b border-border/60 flex items-center justify-between px-8 shrink-0 bg-background/80 backdrop-blur-sm sticky top-0 z-10">
              <span className="font-semibold text-[15px] text-foreground">Drafting Reply for {selectedLead.company_name}</span>
              <div className="flex items-center gap-3">
                  <CustomSelect
                    value={channel}
                    onValueChange={setChannel}
                    size="sm"
                    className="w-28"
                    triggerClassName="bg-card border-border text-xs rounded-lg px-3 py-1.5 h-8 text-foreground"
                    options={[
                      { value: "email", label: "Email" },
                      { value: "linkedin", label: "LinkedIn" },
                    ]}
                  />
                  <CustomSelect
                    value={objectionType}
                    onValueChange={setObjectionType}
                    size="sm"
                    className="w-36"
                    triggerClassName="bg-card border-border text-xs rounded-lg px-3 py-1.5 h-8 text-foreground"
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
            <div className="px-8 py-3 flex items-center justify-between gap-2 text-xs text-muted-foreground border-b border-border/40 shrink-0">
              <div className="flex items-center gap-2">
                <Home size={12} />
                <ChevronRight size={12} />
                <span>Agency</span>
                <ChevronRight size={12} />
                <span className="text-foreground">Ryan</span>
                <ChevronRight size={12} />
                <span className="text-foreground">{selectedLead.kdm_first || 'Unknown'}</span>
              </div>
              <div className="flex items-center gap-2">
                 <span className="px-2 py-0.5 rounded-full bg-muted border border-border/60 uppercase text-[9px] text-muted-foreground font-medium">
                   {selectedLead.status.replace('_', ' ')}
                 </span>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <div className="max-w-[800px] mx-auto space-y-8">
                
                {/* Context Bubble (System) */}
                <div className="flex flex-col items-center">
                  <div className="text-xs text-muted-foreground mb-2">Lead Context Loaded</div>
                  <div className="bg-card border border-border/60 rounded-lg p-4 max-w-full text-muted-foreground text-[13px] leading-relaxed w-full">
                    <p className="font-medium text-foreground mb-1">{selectedLead.company_name} - {selectedLead.kdm_first} ({selectedLead.job_title})</p>
                    <p>{selectedLead.company_description}</p>
                  </div>
                </div>

                {/* History Bubbles */}
                {safeHistory.map((msg) => (
                   <div key={msg.id} className="space-y-6">
                     {/* Prospect Message */}
                     <div className="flex justify-end">
                       <div className="bg-muted/80 border border-border text-foreground px-5 py-3.5 rounded-lg max-w-[85%] whitespace-pre-wrap leading-relaxed shadow-xs">
                         {msg.prospect_message}
                       </div>
                     </div>

                     {/* AI Draft Message */}
                     <div className="flex justify-start items-start gap-4">
                       <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20 shrink-0 mt-1 text-primary">
                         <ElesiumLogo size={14} />
                       </div>
                       <div className="flex flex-col items-start max-w-[85%] relative group">
                         <div className="bg-card border border-border/60 text-foreground px-5 py-3.5 rounded-lg whitespace-pre-wrap leading-relaxed shadow-xs">
                           {msg.ai_draft}
                         </div>
                         <div className="flex items-center gap-2 mt-2">
                           <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-md border border-border/60 uppercase">
                             {msg.channel}
                           </span>
                           {msg.objection_type !== 'none' && (
                             <span className="text-[10px] text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-md border border-border/60 uppercase">
                               Obj: {msg.objection_type}
                             </span>
                           )}
                           <button 
                             type="button"
                             onClick={() => {
                               navigator.clipboard.writeText(msg.ai_draft);
                               toast.success("Copied to clipboard!");
                             }}
                             className="text-[10px] text-muted-foreground bg-muted hover:bg-muted/80 hover:text-foreground px-2 py-0.5 rounded-md border border-border/60 uppercase transition-colors opacity-0 group-hover:opacity-100 flex items-center gap-1 cursor-pointer"
                           >
                             <Check size={10} /> Copy Draft
                           </button>
                         </div>
                       </div>
                     </div>
                   </div>
                ))}
              </div>
            </div>

            {/* Input Area */}
            <div className="p-6 shrink-0 bg-gradient-to-t from-background via-background to-transparent pt-12">
              <div className="max-w-[800px] mx-auto relative">
                <div className="relative flex items-center bg-card border border-border rounded-lg p-2 pl-4 shadow-xs focus-within:border-border transition-colors">
                  <button type="button" aria-label="Attach file" className="text-muted-foreground hover:text-foreground mr-3 shrink-0 transition-colors">
                    <Paperclip size={18} />
                  </button>
                  <input 
                    type="text" 
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isDrafting}
                    placeholder="Paste the prospect's reply here..." 
                    className="flex-1 bg-transparent border-none text-foreground focus:outline-none placeholder:text-muted-foreground py-2 disabled:opacity-50"
                  />
                  <button type="button" aria-label="Voice input" className="text-muted-foreground hover:text-foreground mx-3 shrink-0 transition-colors">
                    <Mic size={18} />
                  </button>
                  <button 
                    type="button"
                    onClick={handleDraftReply}
                    disabled={!inputText.trim() || isDrafting}
                    className="w-8 h-8 shrink-0 rounded-md bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground flex items-center justify-center text-primary-foreground transition-colors"
                    aria-label="Send message"
                  >
                    {isDrafting ? <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" /> : <ArrowUp size={16} />}
                  </button>
                </div>
                <div className="mt-3 text-center text-[10px] text-muted-foreground">
                  Ryan will read the context and draft a response based on the selected channel and objection type.
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground relative">
            <div className="w-16 h-16 rounded-xl bg-card border border-border/60 flex items-center justify-center mb-4 z-10 relative shadow-xs">
              <MessageSquare size={24} className="text-muted-foreground" />
            </div>
            <p className="text-sm z-10 relative">Select a conversation from the sidebar to view history or draft a reply.</p>
          </div>
        )}
      </div>
    </div>
  );
}
