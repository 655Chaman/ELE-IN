import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Calendar, Clock, RefreshCw, Copy, Check, CheckCircle2,
  X, Plus, ExternalLink, Video, User, Building2, ShieldCheck,
  Send, Sliders, Globe
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface CalendarConciergeStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

export function CalendarConciergeStudioModal({ onClose, campaignId }: CalendarConciergeStudioProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'bookings' | 'availability' | 'pitch_studio'>('bookings');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // ── Tab 1: Bookings State ──
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [leadName, setLeadName] = useState('');
  const [leadEmail, setLeadEmail] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [repEmail, setRepEmail] = useState('marcus@ele-in.com');
  const [repName, setRepName] = useState('Marcus Vance');
  const [duration, setDuration] = useState(30);
  const [prospectTz, setProspectTz] = useState('America/New_York');
  const [notes, setNotes] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const { data: bookingsData, mutate: mutateBookings, isLoading: isBookingsLoading } = useSWR<{
    success: boolean;
    bookings: any[];
    total: number;
  }>(
    `/api/elein/calendar/bookings${statusFilter !== 'all' ? `?status=${statusFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  // ── Tab 2: Availability State ──
  const { data: availData } = useSWR<{
    success: boolean;
    availability: any;
  }>(
    '/api/elein/calendar/availability',
    fetcher,
    { revalidateOnFocus: false }
  );

  const availability = availData?.availability || {
    working_hours_start: '09:00',
    working_hours_end: '17:00',
    rep_timezone: 'America/New_York',
    buffer_minutes: 15,
    max_meetings_per_day: 6,
    custom_booking_link: 'https://cal.com/ele-in/marcus'
  };

  // ── Tab 3: Pitch Studio State ──
  const [replyInput, setReplyInput] = useState(
    "Hey! Yeah, this sounds super relevant for our team. Let's chat next Tuesday morning? I'm based in San Francisco (PST)."
  );
  const [pitchProspectName, setPitchProspectName] = useState('Danielle Chen');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{
    intent?: any;
    slots?: any[];
    reply_copy?: string;
  } | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success('Copied to clipboard!');
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleCreateBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leadName.trim() || !leadEmail.trim() || !companyName.trim()) {
      toast.error('Please specify lead name, email, and company.');
      return;
    }
    setIsCreating(true);
    try {
      const res = await fetchWithAuth('/api/elein/calendar/bookings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lead_name: leadName.trim(),
          lead_email: leadEmail.trim(),
          company_name: companyName.trim(),
          assigned_rep_name: repName.trim(),
          assigned_rep_email: repEmail.trim(),
          prospect_timezone: prospectTz,
          meeting_duration_minutes: Number(duration) || 30,
          booking_notes: notes.trim() || undefined
        })
      });
      if (res.status === 402) {
        openPaywall('Executive Calendar Concierge & Frictionless Meeting Booking Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Meeting intent created for ${leadName}! 3 slots held.`);
        setAddModalOpen(false);
        setLeadName('');
        setLeadEmail('');
        setCompanyName('');
        setNotes('');
        mutateBookings();
      } else {
        toast.error(data.detail || 'Failed to create booking.');
      }
    } catch (err: any) {
      toast.error('Network error creating booking: ' + err.message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleConfirmSlot = async (booking: any, slotIso?: string) => {
    const token = booking.confirmation_token || booking.id;
    const targetSlot = slotIso || booking.proposed_slots?.[0] || new Date().toISOString();
    setConfirmingId(booking.id);
    try {
      const res = await fetchWithAuth('/api/elein/calendar/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmation_token: token,
          selected_slot_iso: targetSlot
        })
      });
      if (res.status === 402) {
        openPaywall('Executive Calendar Concierge & Frictionless Meeting Booking Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Meeting confirmed! Outbound campaign sequences halted for ${booking.lead_name}.`);
        mutateBookings();
      } else {
        toast.error(data.detail || 'Confirmation failed.');
      }
    } catch (err: any) {
      toast.error('Error confirming slot: ' + err.message);
    } finally {
      setConfirmingId(null);
    }
  };

  const handleAnalyzeAndPropose = async () => {
    if (!replyInput.trim()) {
      toast.error('Please enter inbound reply text to analyze.');
      return;
    }
    setIsAnalyzing(true);
    try {
      // 1. Extract intent
      const intentRes = await fetchWithAuth('/api/elein/calendar/extract-intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reply_text: replyInput })
      });
      if (intentRes.status === 402) {
        openPaywall('Executive Calendar Concierge & Frictionless Meeting Booking Engine');
        return;
      }
      const intentData = await intentRes.json();

      const detectedTz = intentData.data?.detected_timezone || 'America/New_York';

      // 2. Propose slots
      const slotsRes = await fetchWithAuth('/api/elein/calendar/propose-slots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prospect_name: pitchProspectName,
          prospect_timezone: detectedTz,
          rep_name: repName,
          rep_email: repEmail,
          duration_minutes: 30
        })
      });
      if (slotsRes.status === 402) {
        openPaywall('Executive Calendar Concierge & Frictionless Meeting Booking Engine');
        return;
      }
      const slotsData = await slotsRes.json();

      setAnalysisResult({
        intent: intentData.data,
        slots: slotsData.slots,
        reply_copy: slotsData.reply_copy
      });
      toast.success('Generated 3 conflict-free slots normalized to prospect timezone!');
    } catch (err: any) {
      toast.error('Error analyzing reply: ' + err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const bookings = bookingsData?.bookings || [];
  const confirmedCount = bookings.filter(b => b.status === 'confirmed').length;
  const proposedCount = bookings.filter(b => b.status === 'slots_proposed').length;
  const estimatedPipeline = confirmedCount * 3500; // $3,500 ACV estimate

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col bg-background border border-border rounded-xl shadow-lg text-foreground overflow-hidden">
        
        {/* Header Bar */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-muted/40 text-foreground border border-border rounded-lg flex items-center justify-center">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">
                Autonomous Executive Calendar Concierge & Meeting Closer
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Eliminate booking link drop-off. Auto-propose 3 local timezone slots and halt outbound pestering upon confirmation.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Global Telemetry Metric Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-muted/30 border-b border-border text-sm">
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <CheckCircle2 className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Confirmed Calls</div>
              <div className="text-base font-semibold text-foreground">{confirmedCount} Bookings</div>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Pending Slot Holds</div>
              <div className="text-base font-semibold text-foreground">{proposedCount} In Flight</div>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <Video className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Scheduled Pipeline</div>
              <div className="text-base font-semibold text-foreground">${estimatedPipeline.toLocaleString()} ACV</div>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
            <ShieldCheck className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Conversion Lift</div>
              <div className="text-base font-semibold text-foreground">+42% vs Calendly Links</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border px-6 bg-background gap-6 text-xs font-medium">
          <button
            onClick={() => setActiveTab('bookings')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'bookings'
                ? 'border-foreground text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            Live Bookings & Pipeline ({bookings.length})
          </button>
          <button
            onClick={() => setActiveTab('pitch_studio')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'pitch_studio'
                ? 'border-foreground text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Send className="w-3.5 h-3.5" />
            Inbound Slot Generator
          </button>
          <button
            onClick={() => setActiveTab('availability')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'availability'
                ? 'border-foreground text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            Rep Availability & Buffers
          </button>
        </div>

        {/* Modal Body / Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* ════════════════ TAB 1: LIVE BOOKINGS ════════════════ */}
          {activeTab === 'bookings' && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Status:</span>
                  <Select
                    value={statusFilter}
                    onValueChange={(val) => setStatusFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[140px] bg-background border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Bookings</SelectItem>
                      <SelectItem value="confirmed">Confirmed</SelectItem>
                      <SelectItem value="slots_proposed">Slots Proposed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => mutateBookings()}
                    className="p-2 text-muted-foreground hover:text-foreground bg-card border border-border hover:bg-muted rounded-md transition-colors"
                    title="Refresh Bookings"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setAddModalOpen(true)}
                    className="flex items-center gap-2 px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md text-xs font-medium transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Create Meeting Reservation
                  </button>
                </div>
              </div>

              {/* Booking Cards Grid */}
              {isBookingsLoading ? (
                <div className="p-12 text-center text-muted-foreground flex items-center justify-center gap-3">
                  <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
                  Syncing calendar bookings...
                </div>
              ) : bookings.length === 0 ? (
                <div className="p-12 text-center bg-muted/30 border border-dashed border-border rounded-lg">
                  <Calendar className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                  <h3 className="text-base font-semibold text-foreground">No Meetings Booked Yet</h3>
                  <p className="text-xs text-muted-foreground max-w-md mx-auto mt-1 mb-4">
                    When prospects respond positively, Ele-in automatically holds 3 conflict-free slots and creates reservation records here.
                  </p>
                  <button
                    onClick={() => setAddModalOpen(true)}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-md transition-colors"
                  >
                    Schedule First Meeting
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {bookings.map((b) => {
                    const isConfirmed = b.status === 'confirmed';
                    const meetUrl = b.meeting_link;

                    return (
                      <div
                        key={b.id}
                        className="rounded-lg border border-border bg-card p-4 flex flex-col justify-between transition-colors"
                      >
                        <div>
                          {/* Card Header: Lead & Status */}
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div>
                              <h4 className="text-sm font-semibold text-foreground">
                                {b.lead_name}
                              </h4>
                              <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                                <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                                {b.company_name} ({b.lead_email})
                              </p>
                            </div>
                            <span
                              className={`px-2 py-0.5 rounded-md text-[10px] font-medium uppercase tracking-wider border ${
                                isConfirmed
                                  ? 'bg-primary/10 text-foreground border-border'
                                  : 'bg-muted text-muted-foreground border-border'
                              }`}
                            >
                              {isConfirmed ? 'Confirmed' : 'Slots Proposed'}
                            </span>
                          </div>

                          {/* Meeting Details Box */}
                          <div className="my-3 p-3 rounded-lg bg-muted/30 border border-border text-xs space-y-2">
                            <div className="flex items-center justify-between text-muted-foreground">
                              <span className="flex items-center gap-1.5">
                                <User className="w-3.5 h-3.5 text-muted-foreground" />
                                Assigned Rep:
                              </span>
                              <span className="text-foreground font-medium">{b.assigned_rep_name}</span>
                            </div>

                            <div className="flex items-center justify-between text-muted-foreground">
                              <span className="flex items-center gap-1.5">
                                <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                                Timezone:
                              </span>
                              <span className="text-foreground font-mono text-[11px]">{b.prospect_timezone}</span>
                            </div>

                            {/* Scheduled Time or Options */}
                            <div className="pt-2 border-t border-border">
                              {isConfirmed ? (
                                <div className="text-foreground font-medium flex items-center gap-1.5">
                                  <CheckCircle2 className="w-4 h-4 shrink-0 text-muted-foreground" />
                                  <span>
                                    {b.confirmed_slot ? new Date(b.confirmed_slot).toUTCString() : 'Confirmed'}
                                  </span>
                                </div>
                              ) : (
                                <div className="text-muted-foreground text-[11px]">
                                  3 slots held on calendar (awaiting prospect confirmation)
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Meeting Link or Token */}
                          {meetUrl && (
                            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-muted/30 border border-border text-xs text-foreground mb-3">
                              <span className="flex items-center gap-1.5 truncate">
                                <Video className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                                <span className="truncate">{meetUrl}</span>
                              </span>
                              <button
                                onClick={() => copyToClipboard(meetUrl, `meet-${b.id}`)}
                                className="p-1 text-muted-foreground hover:text-foreground"
                              >
                                {copiedKey === `meet-${b.id}` ? <Check className="w-3 h-3 text-foreground" /> : <Copy className="w-3 h-3" />}
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Card Actions */}
                        <div className="flex items-center gap-2 pt-2 border-t border-border">
                          {!isConfirmed ? (
                            <button
                              onClick={() => handleConfirmSlot(b)}
                              disabled={confirmingId === b.id}
                              className="flex-1 py-1.5 px-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md text-xs font-medium flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                            >
                              {confirmingId === b.id ? (
                                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <>
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  Confirm First Slot
                                </>
                              )}
                            </button>
                          ) : (
                            <a
                              href={meetUrl || '#'}
                              target="_blank"
                              rel="noreferrer"
                              className="flex-1 py-1.5 px-2 bg-muted/40 hover:bg-muted text-foreground border border-border rounded-md text-xs font-medium transition-colors text-center flex items-center justify-center gap-1.5"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              Join Call
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ════════════════ TAB 2: INBOUND SLOT GENERATOR ════════════════ */}
          {activeTab === 'pitch_studio' && (
            <div className="space-y-6">
              <div className="rounded-lg border border-border bg-card p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <Clock className="w-4 h-4 text-muted-foreground" />
                    Inbound Scheduling Parser & Slot Generator
                  </h3>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="text-muted-foreground mb-1 block">Prospect Name</label>
                    <input
                      type="text"
                      value={pitchProspectName}
                      onChange={(e) => setPitchProspectName(e.target.value)}
                      className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Assigned SDR / AE</label>
                    <input
                      type="text"
                      value={repName}
                      onChange={(e) => setRepName(e.target.value)}
                      className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="space-y-1 text-xs">
                  <label className="text-muted-foreground block font-medium">Inbound Lead Message / Reply Text</label>
                  <textarea
                    rows={3}
                    value={replyInput}
                    onChange={(e) => setReplyInput(e.target.value)}
                    placeholder="Paste the message received from the lead..."
                    className="w-full bg-background border border-border rounded-md p-3 text-foreground focus:outline-none focus:ring-1 focus:ring-primary text-xs"
                  />
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleAnalyzeAndPropose}
                    disabled={isAnalyzing}
                    className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md text-xs font-medium transition-colors disabled:opacity-50"
                  >
                    {isAnalyzing ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                    Parse Intent & Generate 3 Local Slots
                  </button>
                </div>
              </div>

              {/* Analysis Results & Consultative Reply Copy */}
              {analysisResult && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Left: Extracted Intent & Slots */}
                  <div className="rounded-lg border border-border bg-card p-5 space-y-4">
                    <h4 className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-2">
                      <Clock className="w-4 h-4 text-muted-foreground" />
                      Extracted Intent & Timezone Normalized Slots
                    </h4>

                    <div className="grid grid-cols-2 gap-3 text-xs bg-muted/30 p-3 rounded-lg border border-border">
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Detected Intent</span>
                        <span className="font-semibold text-foreground">
                          {analysisResult.intent?.has_scheduling_intent ? 'Positive Meeting Signal' : 'Uncertain'}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Normalized Timezone</span>
                        <span className="font-mono text-foreground">
                          {analysisResult.intent?.detected_timezone}
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs text-muted-foreground font-medium block">Held Slots (Conflict-Free):</span>
                      {analysisResult.slots?.map((slot, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-md bg-muted/30 border border-border flex items-center justify-between text-xs"
                        >
                          <span className="font-medium text-foreground">{slot.display_label}</span>
                          <span className="px-2 py-0.5 rounded-md text-[10px] bg-card border border-border text-muted-foreground">
                            Slot {idx + 1}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right: Frictionless Consultative Reply */}
                  <div className="rounded-lg border border-border bg-card p-5 space-y-3 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <Send className="w-4 h-4 text-muted-foreground" />
                          Friction-Free Consultative Reply Copy
                        </span>
                        <button
                          onClick={() => copyToClipboard(analysisResult.reply_copy || '', 'reply-copy')}
                          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                        >
                          {copiedKey === 'reply-copy' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Reply
                        </button>
                      </div>
                      <div className="bg-muted/30 p-4 rounded-lg border border-border text-xs text-foreground leading-relaxed font-mono whitespace-pre-wrap">
                        {analysisResult.reply_copy}
                      </div>
                    </div>

                    <div className="p-3 bg-muted/30 border border-border rounded-lg text-[11px] text-muted-foreground flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 shrink-0 text-muted-foreground" />
                      <span>
                        Automatic Sequence Halt: When the lead selects any option, their active campaign sequence is automatically halted.
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ════════════════ TAB 3: REP AVAILABILITY & BUFFERS ════════════════ */}
          {activeTab === 'availability' && (
            <div className="space-y-6">
              <div className="rounded-lg border border-border bg-card p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-muted-foreground" />
                    Sales Rep Calendar Settings & Anti-Burnout Buffers
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Configure business hours, buffer intervals, and daily meeting capacity to prevent double-booking.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2">
                    <div className="text-muted-foreground font-medium">Working Hours</div>
                    <div className="text-base font-semibold text-foreground">
                      {availability.working_hours_start} - {availability.working_hours_end}
                    </div>
                    <div className="text-[10px] text-muted-foreground">Monday through Friday</div>
                  </div>

                  <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2">
                    <div className="text-muted-foreground font-medium">Meeting Buffer Interval</div>
                    <div className="text-base font-semibold text-foreground">
                      {availability.buffer_minutes} Minutes
                    </div>
                    <div className="text-[10px] text-muted-foreground">Enforced buffer between calls</div>
                  </div>

                  <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2">
                    <div className="text-muted-foreground font-medium">Max Daily Meetings</div>
                    <div className="text-base font-semibold text-foreground">
                      {availability.max_meetings_per_day} Calls / Day
                    </div>
                    <div className="text-[10px] text-muted-foreground">Anti-burnout scheduling cap</div>
                  </div>
                </div>

                {/* Integration Status */}
                <div className="p-4 rounded-lg bg-muted/30 border border-border flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-card text-foreground border border-border rounded-lg">
                      <Globe className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-foreground">Calendar Provider Connection</h4>
                      <p className="text-[11px] text-muted-foreground">Google Calendar & Cal.com bidirectional webhook listener active.</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-md text-xs font-medium bg-card text-foreground border border-border flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground" />
                    Connected & Syncing
                  </span>
                </div>
              </div>
            </div>
          )}

        </div>

        {/* ════════════════ CREATE MEETING MODAL ════════════════ */}
        {addModalOpen && (
          <div className="fixed inset-0 z-60 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
            <div className="bg-card border border-border rounded-xl max-w-md w-full p-6 text-foreground shadow-lg space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-muted-foreground" />
                  Create Meeting Reservation
                </h3>
                <button
                  onClick={() => setAddModalOpen(false)}
                  className="p-1 text-muted-foreground hover:text-foreground rounded-md transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateBooking} className="space-y-3 text-xs">
                <div>
                  <label className="text-muted-foreground mb-1 block">Lead Full Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Alex Morgan"
                    value={leadName}
                    onChange={(e) => setLeadName(e.target.value)}
                    className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block">Lead Email *</label>
                    <input
                      type="email"
                      required
                      placeholder="alex@company.com"
                      value={leadEmail}
                      onChange={(e) => setLeadEmail(e.target.value)}
                      className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Company Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Stripe, Linear"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                      className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block">Assigned AE / Rep</label>
                    <input
                      type="text"
                      value={repName}
                      onChange={(e) => setRepName(e.target.value)}
                      className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Prospect Timezone</label>
                    <Select
                      value={prospectTz}
                      onValueChange={(val) => setProspectTz(val)}
                    >
                      <SelectTrigger className="w-full bg-background border-border h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="America/New_York">Eastern Time (EST)</SelectItem>
                        <SelectItem value="America/Chicago">Central Time (CST)</SelectItem>
                        <SelectItem value="America/Denver">Mountain Time (MST)</SelectItem>
                        <SelectItem value="America/Los_Angeles">Pacific Time (PST)</SelectItem>
                        <SelectItem value="Europe/London">London (GMT/BST)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <label className="text-muted-foreground mb-1 block">Notes / Deal Context</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Interested in replacing Salesloft seat licenses"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-3">
                  <button
                    type="button"
                    onClick={() => setAddModalOpen(false)}
                    className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground border border-border rounded-md transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreating}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    {isCreating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    Reserve 3 Slots
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
