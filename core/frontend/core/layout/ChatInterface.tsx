import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState } from 'react';
import { BackgroundBeams } from '@/components/ui/background-beams';
import useSWR from 'swr';
import { 
  Search, Plus, Paperclip, Mic, ArrowUp, MessageSquare, PanelLeftClose, Home, ChevronRight, Check
} from 'lucide-react';
import { toast } from 'sonner';
import { friendlyToast } from '../../components/FriendlyError';

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
      <div className="w-[280px] bg-[#111318] border-r border-white/[0.05] flex flex-col shrink-0">
        <div className="h-[60px] flex items-center justify-between px-4 border-b border-white/[0.05] shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-zinc-500/20 flex items-center justify-center border border-zinc-500/30">
              <MessageSquare size={16} className="text-zinc-400" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-white">Ryan</span>
              <span className="text-[11px] text-zinc-500">History ({safeLeads.length})</span>
            </div>
          </div>
          <button className="text-zinc-500 hover:text-white transition-colors">
            <PanelLeftClose size={16} />
          </button>
        </div>

        <div className="p-4 space-y-4 shrink-0">
          <button 
            onClick={() => { setSelectedLeadId(null); setInputText(""); }}
            className="w-full flex items-center justify-center gap-2 py-2 bg-white/[0.03] hover:bg-white/[0.05] border border-white/[0.05] rounded-xl text-zinc-300 font-medium transition-colors"
          >
            <Plus size={16} />
            <span>New chat</span>
          </button>

          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input 
              type="text" 
              placeholder="Search leads..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#16191f] border border-white/[0.05] rounded-lg py-1.5 pl-9 pr-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-white/[0.1]"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-4">
          {filteredLeads.map(lead => (
            <button 
              key={lead.id}
              onClick={() => setSelectedLeadId(lead.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-left transition-colors ${
                selectedLeadId === lead.id 
                  ? 'bg-white/[0.03] text-zinc-400' 
                  : 'text-zinc-400 hover:bg-white/[0.02] hover:text-zinc-200'
              }`}
            >
              <MessageSquare size={14} className="shrink-0" />
              <div className="flex flex-col truncate w-full">
                <span className="truncate">{lead.company_name || 'Unknown Company'}</span>
                {lead.kdm_first && (
                  <span className={`text-[10px] ${selectedLeadId === lead.id ? 'text-zinc-500/80' : 'text-zinc-500'} truncate`}>
                    {lead.kdm_first} • {lead.job_title}
                  </span>
                )}
              </div>
            </button>
          ))}
          {filteredLeads.length === 0 && (
             <div className="text-center text-xs text-zinc-500 py-4">No active leads found.</div>
          )}
        </div>
      </div>

      {/* Right Column: Chat Area */}
      <div className="flex-1 bg-[#0f1115] flex flex-col relative overflow-hidden">
        {selectedLead ? (
          <>
            {/* Header */}
            <div className="h-[60px] border-b border-white/[0.05] flex items-center justify-between px-8 shrink-0 bg-[#0f1115]/80 backdrop-blur-md sticky top-0 z-10">
              <span className="font-semibold text-[15px] text-white">Drafting Reply for {selectedLead.company_name}</span>
              <div className="flex items-center gap-3">
                 <select
                    value={channel}
                    onChange={(e) => setChannel(e.target.value)}
                    className="bg-[#16191f] border border-white/[0.1] text-xs rounded-lg px-3 py-1.5 focus:outline-none text-zinc-300 transition-colors"
                  >
                    <option value="email">Email</option>
                    <option value="linkedin">LinkedIn</option>
                  </select>
                  <select
                    value={objectionType}
                    onChange={(e) => setObjectionType(e.target.value)}
                    className="bg-[#16191f] border border-white/[0.1] text-xs rounded-lg px-3 py-1.5 focus:outline-none text-zinc-300 transition-colors"
                  >
                    <option value="none">No Objection</option>
                    <option value="timing">Timing</option>
                    <option value="competitor">Competitor</option>
                    <option value="price">Price</option>
                    <option value="not_interested">Not Interested</option>
                  </select>
              </div>
            </div>
            
            {/* Breadcrumbs */}
            <div className="px-8 py-3 flex items-center justify-between gap-2 text-xs text-zinc-500 border-b border-white/[0.02] shrink-0">
              <div className="flex items-center gap-2">
                <Home size={12} />
                <ChevronRight size={12} />
                <span>Agency</span>
                <ChevronRight size={12} />
                <span className="text-zinc-300">Ryan</span>
                <ChevronRight size={12} />
                <span className="text-zinc-300">{selectedLead.kdm_first || 'Unknown'}</span>
              </div>
              <div className="flex items-center gap-2">
                 <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 uppercase text-[9px] text-zinc-400">
                   {selectedLead.status.replace('_', ' ')}
                 </span>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <div className="max-w-[800px] mx-auto space-y-8">
                
                {/* Context Bubble (System) */}
                <div className="flex flex-col items-center">
                  <div className="text-xs text-zinc-500 mb-2">Lead Context Loaded</div>
                  <div className="bg-[#16191f] border border-white/[0.05] rounded-xl p-4 max-w-full text-zinc-400 text-[13px] leading-relaxed w-full">
                    <p className="font-medium text-zinc-300 mb-1">{selectedLead.company_name} - {selectedLead.kdm_first} ({selectedLead.job_title})</p>
                    <p>{selectedLead.company_description}</p>
                  </div>
                </div>

                {/* History Bubbles */}
                {safeHistory.map((msg) => (
                   <div key={msg.id} className="space-y-6">
                     {/* Prospect Message */}
                     <div className="flex justify-end">
                       <div className="bg-[#242938] border border-zinc-500/20 text-zinc-200 px-5 py-3.5 rounded-2xl rounded-tr-sm max-w-[85%] whitespace-pre-wrap leading-relaxed shadow-md">
                         {msg.prospect_message}
                       </div>
                     </div>

                     {/* AI Draft Message */}
                     <div className="flex justify-start items-start gap-4">
                       <div className="w-8 h-8 rounded-lg bg-zinc-500/20 flex items-center justify-center border border-zinc-500/30 shrink-0 mt-1">
                         <MessageSquare size={14} className="text-zinc-400" />
                       </div>
                       <div className="flex flex-col items-start max-w-[85%] relative group">
                         <div className="bg-white/[0.03] border border-white/[0.05] text-zinc-300 px-5 py-3.5 rounded-2xl rounded-tl-sm whitespace-pre-wrap leading-relaxed">
                           {msg.ai_draft}
                         </div>
                         <div className="flex items-center gap-2 mt-2">
                           <span className="text-[10px] text-zinc-500 bg-white/5 px-2 py-0.5 rounded-full border border-white/5 uppercase">
                             {msg.channel}
                           </span>
                           {msg.objection_type !== 'none' && (
                             <span className="text-[10px] text-zinc-400 bg-zinc-500/10 px-2 py-0.5 rounded-full border border-zinc-500/20 uppercase">
                               Obj: {msg.objection_type}
                             </span>
                           )}
                           <button 
                             onClick={() => {
                               navigator.clipboard.writeText(msg.ai_draft);
                               toast.success("Copied to clipboard!");
                             }}
                             className="text-[10px] text-zinc-400 bg-zinc-500/10 hover:bg-zinc-500/20 px-2 py-0.5 rounded-full border border-zinc-500/20 uppercase transition-colors opacity-0 group-hover:opacity-100 flex items-center gap-1"
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
            <div className="p-6 shrink-0 bg-gradient-to-t from-[#0f1115] via-[#0f1115] to-transparent pt-12">
              <div className="max-w-[800px] mx-auto relative">
                <div className="relative flex items-center bg-[#16191f] border border-white/[0.1] rounded-2xl p-2 pl-4 shadow-[0_0_40px_rgba(0,0,0,0.5)] focus-within:border-zinc-500/50 transition-colors">
                  <button className="text-zinc-400 hover:text-white mr-3 shrink-0">
                    <Paperclip size={18} />
                  </button>
                  <input 
                    type="text" 
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isDrafting}
                    placeholder="Paste the prospect's reply here..." 
                    className="flex-1 bg-transparent border-none text-white focus:outline-none placeholder-zinc-500 py-2 disabled:opacity-50"
                  />
                  <button className="text-zinc-400 hover:text-white mx-3 shrink-0">
                    <Mic size={18} />
                  </button>
                  <button 
                    onClick={handleDraftReply}
                    disabled={!inputText.trim() || isDrafting}
                    className="w-8 h-8 shrink-0 rounded-lg bg-zinc-500 hover:bg-zinc-400 disabled:bg-zinc-700 disabled:text-zinc-500 flex items-center justify-center text-white transition-colors"
                  >
                    {isDrafting ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <ArrowUp size={16} />}
                  </button>
                </div>
                <div className="mt-3 text-center text-[10px] text-zinc-500">
                  Ryan will read the context and draft a response based on the selected channel and objection type.
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-zinc-600 relative">
            <div className="w-16 h-16 rounded-2xl bg-[#16191f] border border-white/[0.05] flex items-center justify-center mb-4 z-10 relative">
              <MessageSquare size={24} className="text-zinc-500" />
            </div>
            <p className="text-sm z-10 relative">Select a conversation from the sidebar to view history or draft a reply.</p>
            <BackgroundBeams />
          </div>
        )}
      </div>
    </div>
  );
}
