import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useSWR from 'swr';
import { MessageSquare, Send, Sparkles, RefreshCw, UserCheck, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

;

interface ThreadSummary {
  sender_name: string;
  last_message: string;
  direction: string;
  created_at: string;
  type?: string;
}

interface Message {
  id: string;
  message_text: string;
  direction: string;
  created_at: string;
  type?: string;
}

export function EleInInbox() {
  const { data: threads, mutate: mutateThreads } = useSWR<ThreadSummary[]>("/api/elein/inbox/threads", fetcher);
  const [selectedSender, setSelectedSender] = useState<string | null>(null);

  const { data: messages, mutate: mutateMessages } = useSWR<Message[]>(
    selectedSender ? `/api/elein/inbox/threads/${encodeURIComponent(selectedSender)}` : null,
    fetcher
  );

  const [isSyncing, setIsSyncing] = useState(false);
  
  // Layer 0: New states
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isDraftingAI, setIsDraftingAI] = useState(false);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      toast.info("Scraping inbox... this may take up to 20 seconds as Playwright navigates LinkedIn.");
      const res = await fetchWithAuth("/api/elein/inbox/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: localStorage.getItem("last_used_account_id") || "" }) 
      });
      if (res.ok) {
        toast.success("Inbox sync complete!");
        mutateThreads();
      } else {
        toast.error("Inbox sync failed (did you connect an account?)");
      }
    } catch (error) {
      toast.error("Error connecting to sync engine");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSend = async () => {
    if (!replyText.trim() || isSending || !selectedSender) return;

    setIsSending(true);
    try {
      const res = await fetchWithAuth("/api/elein/inbox/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender_name: selectedSender, message_text: replyText.trim() })
      });

      if (res.ok) {
        setReplyText('');
        toast.success("Reply sent");
        mutateMessages();
        mutateThreads();
      } else {
        throw new Error("Failed response");
      }
    } catch (error) {
      toast.error("Failed to send reply. Your draft has been preserved — please try again.");
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSparklesClick = async () => {
    setIsDraftingAI(true);
    // Simulate slight delay for AI draft
    setTimeout(() => {
      setReplyText("Thanks for following up! I'd love to chat — how does this Thursday look for a quick 15-minute call?");
      setIsDraftingAI(false);
    }, 400);
  };

  const safeThreads = Array.isArray(threads) ? threads : [];
  const safeMessages = Array.isArray(messages) ? messages : [];

  const navigate = useNavigate();

  if (threads !== undefined && safeThreads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-64px)] bg-[#0B0C0E] text-white">
        <div className="flex flex-col items-center justify-center text-center p-10 max-w-md bg-surface/20 border border-white/5 rounded-3xl backdrop-blur-md">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 border border-primary/20">
            <MessageSquare size={32} className="text-primary" />
          </div>
          <h2 className="text-xl font-bold mb-2">Your inbox is quiet right now</h2>
          <p className="text-sm text-zinc-400 mb-8 leading-relaxed">
            When prospects reply to your outreach campaigns, their messages will appear here. The AI will analyze each reply and suggest the perfect response.
          </p>
          <div className="flex gap-4">
            <button 
              onClick={() => navigate('/elein/campaigns')}
              className="px-6 py-3 bg-primary/10 hover:bg-primary/20 text-primary text-sm font-semibold rounded-xl transition-colors border border-primary/20"
            >
              Launch a Campaign
            </button>
            <button 
              onClick={handleSync}
              disabled={isSyncing}
              className="flex items-center gap-2 px-6 py-3 bg-primary hover:bg-primary/90 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-primary/20 disabled:opacity-50"
            >
              <RefreshCw size={16} className={isSyncing ? "animate-spin" : ""} />
              <span>Sync Inbox</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-64px)] bg-[#0B0C0E] text-white">
      {/* LEFT PANE - THREAD LIST */}
      <div className="w-[380px] border-r border-white/5 flex flex-col bg-surface/20">
        <div className="p-4 border-b border-white/5 bg-surface/40 backdrop-blur-md sticky top-0 flex justify-between items-center">
          <h2 className="text-lg font-medium tracking-tight">LinkedIn Inbox</h2>
          <button 
            onClick={handleSync}
            disabled={isSyncing}
            className="flex items-center gap-2 px-3 py-1.5 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white disabled:opacity-50 text-sm font-medium"
            title="Sync latest messages via Playwright"
          >
            <RefreshCw size={16} className={isSyncing ? "animate-spin" : ""} />
            <span>Sync</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {safeThreads.length === 0 && (
            <div className="p-8 text-center text-zinc-500 text-sm">
              No threads found. Click "Sync" to scrape LinkedIn.
            </div>
          )}
          {safeThreads.map(thread => (
            <div
              key={thread.sender_name}
              onClick={() => {
                setSelectedSender(thread.sender_name);
                setReplyText(''); // Clear draft when switching threads
              }}
              className={`p-4 border-b border-white/5 cursor-pointer transition-all duration-200 ${
                selectedSender === thread.sender_name 
                  ? 'bg-primary/10 border-l-2 border-l-primary' 
                  : 'hover:bg-white/5 border-l-2 border-l-transparent'
              }`}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="font-semibold text-zinc-200">{thread.sender_name}</span>
                <span className="text-xs text-zinc-500">
                  {new Date(thread.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="text-sm text-zinc-400 line-clamp-2 leading-relaxed flex items-center gap-1.5">
                {thread.type === 'connection_accepted' ? (
                  <><UserCheck size={14} className="text-primary" /> <span className="italic text-primary/80">Connection Accepted</span></>
                ) : (
                  <>{thread.direction === 'outbound' ? 'You: ' : ''}{thread.last_message}</>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT PANE - THREAD DETAILS */}
      <div className="flex-1 flex flex-col bg-surface/10">
        {!selectedSender ? (
          <div className="flex-1 flex flex-col items-center justify-center text-zinc-500">
            <MessageSquare size={48} className="mb-4 opacity-20" />
            <p>Select a thread to view message history</p>
          </div>
        ) : (
          <>
            <div className="p-6 border-b border-white/5 bg-surface/40 backdrop-blur-md">
              <h2 className="text-xl font-bold text-white">{selectedSender}</h2>
              <div className="flex items-center gap-2 text-sm text-zinc-400 mt-1">
                <span>LinkedIn Conversation</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {safeMessages.map(msg => {
                if (msg.type === "connection_accepted") {
                  return (
                    <div key={msg.id} className="flex justify-center my-4">
                      <div className="px-4 py-2 bg-primary/10 border border-primary/20 rounded-full flex items-center gap-2 text-xs font-medium text-primary shadow-sm">
                        <UserCheck size={14} />
                        <span>Connection Accepted</span>
                        <span className="opacity-50 ml-2">{new Date(msg.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={msg.id} className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[70%] rounded-2xl p-4 ${
                      msg.direction === 'outbound' 
                        ? 'bg-primary/20 text-primary-foreground border border-primary/20 rounded-tr-sm' 
                        : 'bg-zinc-800/50 text-zinc-200 border border-white/5 rounded-tl-sm'
                    }`}>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.message_text}</p>
                      <div className="mt-2 text-[10px] opacity-50 flex items-center justify-end gap-1">
                        {new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="p-4 border-t border-white/5 bg-surface/40 backdrop-blur-md">
              <div className="flex items-center gap-2 p-2 rounded-xl bg-black/40 border border-white/10">
                <input 
                  type="text" 
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a reply, or click Sparkles for AI Copilot... (Press Enter to send)"
                  maxLength={4000}
                  className="flex-1 bg-transparent border-none outline-none text-sm px-2 text-white placeholder-zinc-500 disabled:opacity-50"
                  disabled={isSending}
                />
                <button 
                  onClick={handleSparklesClick}
                  disabled={isSending || isDraftingAI} 
                  className="p-2 bg-primary/20 text-primary hover:bg-primary/30 transition-colors rounded-lg disabled:opacity-50"
                >
                  {isDraftingAI ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                </button>
                <button 
                  onClick={handleSend}
                  disabled={!replyText.trim() || isSending} 
                  className="p-2 bg-primary text-white hover:bg-primary/90 transition-colors rounded-lg disabled:opacity-50 disabled:bg-zinc-800 disabled:text-zinc-500"
                >
                  {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
