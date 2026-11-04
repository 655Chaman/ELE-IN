import { useState, useRef, useEffect } from "react";
import { 
  Users, UserPlus, Loader2, ChevronDown, Check, X, 
  Shield, Mail, Crown, User as UserIcon, Trash2, AlertTriangle, Clock,
  Zap, ArrowRight, Lock, Copy, Briefcase, BarChart3, Send, RotateCcw, Sliders
} from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner"
import { friendlyToast } from "../../components/FriendlyError";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { useAuth } from "@/lib/AuthContext";
import { usePaywall } from "@/contexts/PaywallContext";
import { motion, AnimatePresence } from "motion/react";
import { format } from "date-fns";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { CustomSelect } from "@/components/ui/select";

export type Role = "owner" | "admin" | "manager" | "sender" | "analyst" | "member";

const ROLE_SUBTITLES: Record<Role, { subtitle: string }> = {
  owner: { subtitle: "Full access and billing" },
  admin: { subtitle: "Can edit settings" },
  manager: { subtitle: "Can manage campaigns & leads" },
  sender: { subtitle: "Can review & send messages" },
  analyst: { subtitle: "Can view analytics & reports" },
  member: { subtitle: "View only access" }
};

interface Member {
  user_id: string;
  role: Role;
  display_name: string;
  created_at: string;
  last_active_at?: string;
  permissions?: {
    can_export_leads?: boolean;
    can_delete_campaigns?: boolean;
    can_manage_billing?: boolean;
    can_connect_accounts?: boolean;
  };
}

interface Invite {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  status: string;
  token?: string;
}

export function TeamSettings({ workspaceId }: { workspaceId: string | null }) {
  const { user } = useAuth();
  const { openPaywall } = usePaywall();
  const { data, mutate, isLoading, error } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/members` : null,
    fetcher
  );

  const { data: billingData } = useSWR<{ tier?: string }>(
    workspaceId ? `/api/elein/workspaces/billing?workspace_id=${workspaceId}` : null,
    fetcher
  );
  const tier = (billingData?.tier || 'FREE').toUpperCase();
  const isEnterprise = tier === 'ENTERPRISE';
  const isAgency = tier === 'AGENCY';
  const isPro = tier === 'PRO' || tier === 'GROWTH' || isAgency || isEnterprise;
  const maxSeats = isEnterprise ? 25 : isAgency ? 10 : isPro ? 5 : 1;
  
  const members: Member[] = data?.members || [];
  const invites: Invite[] = data?.invites || [];
  const totalPeople = members.length + invites.length;
  const isSeatCapped = totalPeople >= maxSeats;
  const ownerCount = members.filter(m => m.role === "owner").length;

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteMode, setInviteMode] = useState<"single" | "bulk">("single");
  const [inviteEmail, setInviteEmail] = useState("");
  const [bulkEmailsText, setBulkEmailsText] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const [memberSearchQuery, setMemberSearchQuery] = useState("");
  const [sending, setSending] = useState(false);
  const [createdInviteLink, setCreatedInviteLink] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  
  // Ref for double-submit prevention
  const isSubmittingRef = useRef(false);

  // For inline confirm removal
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);

  // Dropdown state for roles
  const [openRoleDropdown, setOpenRoleDropdown] = useState<string | null>(null);

  // Close dropdowns on outside click (targeted by data attribute to prevent ref collisions in tables)
  useEffect(() => {
    if (!openRoleDropdown) return;
    const handleOutsideClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && !target.closest(`[data-role-dropdown="${openRoleDropdown}"]`)) {
        setOpenRoleDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [openRoleDropdown]);

  const handleInviteToggle = () => {
    if (isSeatCapped) {
      if (!isPro) {
        openPaywall({ featureName: "Team Members & Seats", minTier: "PRO" });
        toast.info("Free plan is limited to 1 member. Upgrade to Growth Pro to invite up to 5 team members.");
      } else if (tier === 'PRO' || tier === 'GROWTH') {
        openPaywall({ featureName: "Agency Team Seats", minTier: "AGENCY" });
        toast.info("Growth Pro is limited to 5 seats. Upgrade to Agency Tier to invite up to 10 team members.");
      } else if (isAgency) {
        openPaywall({ featureName: "Enterprise Team Seats", minTier: "ENTERPRISE" });
        toast.info("Agency plan is limited to 10 seats. Upgrade to Enterprise for 25+ seats.");
      } else {
        toast.error("Seat limit reached for your enterprise plan. Contact support for additional seat licenses.");
      }
      return;
    }
    setShowInviteForm(!showInviteForm);
  };

  const filteredMembers = members.filter((m) => {
    if (!memberSearchQuery.trim()) return true;
    const q = memberSearchQuery.toLowerCase().trim();
    return (
      (m.display_name && m.display_name.toLowerCase().includes(q)) ||
      (m.user_id && m.user_id.toLowerCase().includes(q)) ||
      (m.role && m.role.toLowerCase().includes(q))
    );
  });

  const handleBulkInvite = async () => {
    if (isSubmittingRef.current || !bulkEmailsText.trim() || !workspaceId) return;
    const rawList = bulkEmailsText
      .split(/[\n,;\s]+/)
      .map((e) => e.trim())
      .filter(Boolean);
    if (rawList.length === 0) {
      toast.error("Please enter at least one valid email address.");
      return;
    }

    isSubmittingRef.current = true;
    setSending(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/invites/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ emails: rawList, role: inviteRole }),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(resData.detail || "Bulk invite failed");
      }
      toast.success(`Dispatched ${resData.total_created || 0} invitation(s) successfully!`);
      if (resData.skipped && resData.skipped.length > 0) {
        toast.info(`Skipped ${resData.skipped.length} entry(s) (duplicates or invalid syntax).`);
      }
      setBulkEmailsText("");
      setShowInviteForm(false);
      mutate();
    } catch (e: any) {
      friendlyToast("Failed to send bulk invitations", e);
    } finally {
      setSending(false);
      isSubmittingRef.current = false;
    }
  };

  const handleInvite = async () => {
    if (isSubmittingRef.current || !inviteEmail.trim() || !workspaceId) return;
    
    // Paranoia Layer 1 & 2: Seat Cap check
    if (isSeatCapped) {
      if (!isPro) {
        openPaywall({ featureName: "Team Members & Seats", minTier: "PRO" });
        toast.info("Free plan seat limit reached (1/1). Upgrade to Growth Pro to invite up to 5 team members.");
      } else if (tier === 'PRO' || tier === 'GROWTH') {
        openPaywall({ featureName: "Agency Team Seats", minTier: "AGENCY" });
        toast.info("Growth Pro seat limit reached (5/5). Upgrade to Agency Tier to invite up to 10 team members.");
      } else if (isAgency) {
        openPaywall({ featureName: "Enterprise Team Seats", minTier: "ENTERPRISE" });
        toast.info("Agency plan seat limit reached (10/10). Upgrade to Enterprise for 25+ seats.");
      } else {
        toast.error("Seat limit reached for your enterprise plan. Contact support for additional seat licenses.");
      }
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const cleanEmail = inviteEmail.trim().toLowerCase();
    if (!emailRegex.test(cleanEmail)) {
      toast.error("Please enter a valid email address");
      return;
    }
    
    isSubmittingRef.current = true;
    setSending(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/invites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: cleanEmail, role: inviteRole }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to send invite");
      }
      const resData = await res.json().catch(() => ({}));
      toast.success(`Invite sent to ${cleanEmail}`);
      if (resData?.token) {
        const fullLink = `${window.location.origin}/accept-invite?token=${resData.token}`;
        setCreatedInviteLink(fullLink);
      }
      setInviteEmail("");
      setShowInviteForm(false);
      mutate();
    } catch (e: any) {
      friendlyToast('Failed to send invite — please try again.', e);
    } finally {
      setSending(false);
      isSubmittingRef.current = false;
    }
  };

  const handleRevokeInvite = async (inviteId: string, email: string) => {
    if (!workspaceId || revokingId) return;
    setRevokingId(inviteId);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/invites/${inviteId}`, {
        method: "DELETE"
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to revoke invite");
      }
      toast.success(`Invite for ${email} revoked`);
      mutate();
    } catch (e: any) {
      friendlyToast('Failed to revoke invite — please try again.', e);
    } finally {
      setRevokingId(null);
    }
  };

  // Resend Invite State & Handler
  const [resendingInviteId, setResendingInviteId] = useState<string | null>(null);
  const [resendCooldowns, setResendCooldowns] = useState<Record<string, number>>({});

  useEffect(() => {
    const timer = setInterval(() => {
      setResendCooldowns((prev) => {
        let changed = false;
        const next: Record<string, number> = {};
        for (const [id, sec] of Object.entries(prev)) {
          if (sec > 1) {
            next[id] = sec - 1;
            changed = true;
          } else if (sec === 1) {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleResendInvite = async (inviteId: string, email: string) => {
    if (!workspaceId || resendingInviteId || (resendCooldowns[inviteId] ?? 0) > 0) return;
    setResendingInviteId(inviteId);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/invites/${inviteId}/resend`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Failed to resend invite");
      }
      toast.success(`Invitation email resent to ${email}`);
      setResendCooldowns((prev) => ({ ...prev, [inviteId]: 60 }));
    } catch (e: any) {
      friendlyToast("Failed to resend invitation", e);
    } finally {
      setResendingInviteId(null);
    }
  };

  // Granular Permissions Modal State & Handlers
  const [permissionModalMember, setPermissionModalMember] = useState<Member | null>(null);
  const [memberPermissions, setMemberPermissions] = useState({
    can_export_leads: true,
    can_delete_campaigns: false,
    can_manage_billing: false,
    can_connect_accounts: true,
  });
  const [savingPermissions, setSavingPermissions] = useState(false);

  const openPermissionsModal = (member: Member) => {
    setPermissionModalMember(member);
    setMemberPermissions({
      can_export_leads: member.permissions?.can_export_leads ?? (member.role === "owner" || member.role === "admin"),
      can_delete_campaigns: member.permissions?.can_delete_campaigns ?? (member.role === "owner" || member.role === "admin"),
      can_manage_billing: member.permissions?.can_manage_billing ?? (member.role === "owner"),
      can_connect_accounts: member.permissions?.can_connect_accounts ?? (member.role !== "analyst"),
    });
  };

  const handleSavePermissions = async () => {
    if (!workspaceId || !permissionModalMember || savingPermissions) return;
    setSavingPermissions(true);
    try {
      const res = await fetchWithAuth(
        `/api/workspaces/${workspaceId}/members/${permissionModalMember.user_id}/permissions`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(memberPermissions),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Failed to update member permissions");
      }
      toast.success(`Updated access privileges for ${permissionModalMember.display_name}`);
      mutate();
      setPermissionModalMember(null);
    } catch (e: any) {
      friendlyToast("Failed to save permissions", e);
    } finally {
      setSavingPermissions(false);
    }
  };

  const handleRoleChange = async (targetUserId: string, newRole: Role) => {
    if (!isPro) {
      openPaywall({ featureName: "Role-Based Permissions & Delegation" });
      return;
    }

    // Guard: prevent last owner from being demoted
    const targetMember = members?.find(m => m.user_id === targetUserId);
    if (targetMember?.role === 'owner' && newRole !== 'owner' && ownerCount <= 1) {
      toast.error("Cannot change role: this is the last owner of the workspace.");
      return;
    }

    if (!workspaceId) return;
    setOpenRoleDropdown(null);
    setActingOn(targetUserId);
    try {
      // Phase T Enterprise RBAC Guard endpoint with anti-privilege escalation & anti-lockout
      const res = await fetchWithAuth(
        `/api/elein/workspaces/members/role?workspace_id=${workspaceId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_user_id: targetUserId, new_role: newRole }),
        }
      );
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        const errMsg = errJson?.detail || "Failed to update member role";
        throw new Error(errMsg);
      }
      toast.success("Role updated successfully");
      mutate();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to update role');
    } finally {
      setActingOn(null);
    }
  };

  useEffect(() => {
    if (!confirmRemoveId) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConfirmRemoveId(null);
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [confirmRemoveId]);

  const initiateRemoval = (userId: string) => {
    setConfirmRemoveId(userId);
  };

  const cancelRemoval = () => {
    setConfirmRemoveId(null);
  };

  const handleRemove = async (targetUserId: string, displayName: string) => {
    if (!workspaceId) return;
    // Paranoia Layer 2: Prevent deleting the last workspace owner
    const targetMember = members.find(m => m.user_id === targetUserId);
    if (targetMember?.role === "owner" && ownerCount <= 1) {
      toast.error("Cannot remove member: this is the only owner of the workspace.");
      cancelRemoval();
      return;
    }
    setActingOn(targetUserId);
    try {
      const res = await fetchWithAuth(
        `/api/workspaces/${workspaceId}/members/${targetUserId}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to remove member");
      }
      toast.success(`${displayName} has been removed`);
      cancelRemoval(); // Dismiss ONLY on success
      mutate();
    } catch (e: any) {
      friendlyToast('Failed to remove member — please try again.', e);
    } finally {
      setActingOn(null);
    }
  };

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="Please select a workspace from the sidebar to manage its team members." icon={Shield} />;
  }

  if (error) {
    return (
      <div className="p-6 rounded-xl border border-destructive/20 bg-destructive/5 shadow-sm">
        <div className="flex items-center gap-3 text-destructive">
          <AlertTriangle className="w-5 h-5" />
          <p className="text-sm font-medium">Failed to load team members. Please check your connection.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  const RoleBadge = ({ role }: { role: Role }) => {
    switch (role) {
      case "owner":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
            <Crown size={12} />
            Owner
          </span>
        );
      case "admin":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Shield size={12} />
            Admin
          </span>
        );
      case "manager":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Briefcase size={12} />
            Manager
          </span>
        );
      case "sender":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <Send size={12} />
            Sender
          </span>
        );
      case "analyst":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-violet-500/10 text-violet-400 border border-violet-500/20">
            <BarChart3 size={12} />
            Analyst
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-muted/50 text-muted-foreground border border-border">
            <UserIcon size={12} />
            Member
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card relative overflow-hidden shadow-sm">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-primary/10 rounded-xl border border-primary/20">
              <Users className="text-primary" size={24} />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground">Team & Access</h2>
              <p className="text-sm text-muted-foreground mt-1">Manage who has access to this workspace.</p>
            </div>
          </div>
          
          <button
            type="button"
            onClick={handleInviteToggle}
            className={`flex items-center gap-2 px-5 py-2.5 font-semibold text-sm rounded-lg transition-all shadow-md ${
              isSeatCapped
                ? "bg-muted text-foreground hover:bg-muted/80 border border-border"
                : "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground hover:opacity-90"
            }`}
          >
            {showInviteForm ? (
              <X size={16} />
            ) : isSeatCapped ? (
              <Lock size={15} className="text-amber-500" />
            ) : (
              <UserPlus size={16} />
            )}
            {showInviteForm ? "Close" : isSeatCapped ? (tier === 'FREE' ? "Upgrade to Add Members" : !isEnterprise ? "Upgrade Plan" : "Seat Cap Reached") : "Invite Member"}
          </button>
        </div>

        {/* Just Created Invite Link Banner */}
        {createdInviteLink && (
          <div className="mb-6 p-4 rounded-xl border border-primary/30 bg-primary/10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/20 rounded-lg text-primary">
                <Check size={16} />
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">Invitation Link Generated</p>
                <p className="text-xs text-muted-foreground font-mono break-all mt-0.5">{createdInviteLink}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(createdInviteLink);
                setCopiedLink(true);
                toast.success("Invite link copied to clipboard!");
                setTimeout(() => setCopiedLink(false), 2000);
              }}
              className="px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold flex items-center gap-1.5 hover:bg-primary/90 transition-all shrink-0 cursor-pointer shadow-sm"
            >
              {copiedLink ? <Check size={13} /> : <Copy size={13} />}
              {copiedLink ? "Copied" : "Copy Link"}
            </button>
          </div>
        )}

        {/* Team Seat Limit / Pay Ramp Banner */}
        {!isPro && (
          <div className="mb-6 p-4 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/5 via-primary/[0.02] to-transparent flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-primary/10 rounded-lg text-primary mt-0.5">
                <Zap size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold text-foreground">
                    Team Collaboration & Multi-Seat Access
                  </h4>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${isSeatCapped ? 'bg-amber-500/20 text-amber-500 border border-amber-500/30' : 'bg-primary/10 text-primary'}`}>
                    {totalPeople}/{maxSeats} Seat Used
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 max-w-xl">
                  Free tier includes 1 solo seat. Upgrade to <strong className="text-foreground">Growth Pro</strong> to invite up to 5 team members, assign custom roles, and share campaigns & unified inboxes.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Team Members & Seats" })}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all shadow-sm shrink-0 whitespace-nowrap"
            >
              <span>Unlock 5 Seats</span>
              <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* Invite Form Dropdown Panel */}
        <AnimatePresence>
          {showInviteForm && (
            <motion.div
              initial={{ height: 0, opacity: 0, y: -10 }}
              animate={{ height: "auto", opacity: 1, y: 0 }}
              exit={{ height: 0, opacity: 0, y: -10 }}
              className="overflow-hidden"
            >
              <div className="mb-8 p-6 bg-muted/20 border border-border rounded-xl shadow-inner relative space-y-4">
                {/* Invite Mode Toggle */}
                <div className="flex items-center justify-between pb-3 border-b border-border/50">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setInviteMode("single")}
                      className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                        inviteMode === "single"
                          ? "bg-primary text-primary-foreground shadow-xs"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Single Invitation
                    </button>
                    <button
                      type="button"
                      onClick={() => setInviteMode("bulk")}
                      className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                        inviteMode === "bulk"
                          ? "bg-primary text-primary-foreground shadow-xs"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Bulk Add (List / CSV)
                    </button>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {inviteMode === "single" ? "Invite individual colleague" : "Paste multiple emails at once"}
                  </span>
                </div>

                {inviteMode === "single" ? (
                  <div className="flex flex-col sm:flex-row gap-5 items-end">
                    <div className="flex-1 w-full space-y-2">
                      <label className="text-sm font-semibold text-foreground/80">Email Address</label>
                      <div className="relative group">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" size={16} />
                        <input
                          type="email"
                          value={inviteEmail}
                          onChange={(e) => setInviteEmail(e.target.value)}
                          placeholder="colleague@company.com"
                          className="w-full bg-background border border-border rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 transition-all placeholder:text-muted-foreground/50 text-foreground"
                        />
                      </div>
                    </div>
                    
                    <div className="w-full sm:w-48 space-y-2">
                      <label className="text-sm font-semibold text-foreground/80">Role</label>
                      <div className="relative">
                        <Shield className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground z-10 pointer-events-none" size={16} />
                        <CustomSelect
                          value={inviteRole}
                          onValueChange={(val) => {
                            const roleVal = val as Role;
                            if (roleVal !== "member" && !isPro) {
                              openPaywall({ featureName: "Role-Based Permissions & Delegation" });
                              return;
                            }
                            setInviteRole(roleVal);
                          }}
                          triggerClassName="bg-background border-border rounded-lg pl-9 pr-4 py-2.5 text-sm h-10 text-foreground"
                          options={[
                            { value: "member", label: "Member" },
                            { value: "admin", label: isPro ? "Admin" : "Admin (Growth Pro)" },
                            { value: "owner", label: isPro ? "Owner" : "Owner (Growth Pro)" },
                          ]}
                        />
                      </div>
                    </div>
                    
                    <button
                      type="button"
                      onClick={handleInvite}
                      disabled={sending || !inviteEmail.trim()}
                      className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-2.5 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                    >
                      {sending ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                      Send Invite
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-semibold text-foreground/80">
                        Email Addresses (Separated by commas, spaces, or newlines)
                      </label>
                      <textarea
                        rows={3}
                        value={bulkEmailsText}
                        onChange={(e) => setBulkEmailsText(e.target.value)}
                        placeholder="sara@acme.com, david@acme.com&#10;elena@acme.com"
                        className="w-full bg-background border border-border rounded-xl p-3 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary/20 text-foreground"
                      />
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="w-full sm:w-48 space-y-1">
                        <label className="text-xs font-semibold text-foreground/80">Default Assigned Role</label>
                        <CustomSelect
                          value={inviteRole}
                          onValueChange={(val) => setInviteRole(val as Role)}
                          triggerClassName="bg-background border-border rounded-lg px-3 py-2 text-xs h-9 text-foreground"
                          options={[
                            { value: "member", label: "Member" },
                            { value: "admin", label: "Admin" },
                          ]}
                        />
                      </div>

                      <button
                        type="button"
                        onClick={handleBulkInvite}
                        disabled={sending || !bulkEmailsText.trim()}
                        className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-2.5 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                      >
                        {sending ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                        Dispatch Bulk Invites
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Empty State */}
        {totalPeople === 0 && !isLoading ? (
          <div className="flex flex-col items-center gap-4 py-8">
            <EmptyState 
              title="Build your team" 
              description="Invite colleagues to collaborate. You can assign different roles to control their access to campaigns and settings."
              icon={Users}
            />
            <button
              type="button"
              onClick={() => setShowInviteForm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground font-medium rounded-lg hover:bg-secondary/80 transition-colors"
            >
              <UserPlus size={16} />
              Invite First Member
            </button>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Active Members Table */}
            {members.length > 0 && (
              <div className="mb-8">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pl-1">
                  <div>
                    <h3 className="text-lg font-bold tracking-tight text-foreground">
                      Active Members ({filteredMembers.length}{memberSearchQuery ? ` of ${members.length}` : ""})
                    </h3>
                  </div>
                  <div className="relative w-full sm:w-64">
                    <input
                      type="text"
                      placeholder="Search member by name or role..."
                      value={memberSearchQuery}
                      onChange={(e) => setMemberSearchQuery(e.target.value)}
                      className="w-full px-3 py-1.5 pl-8 bg-background border border-border rounded-lg text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
                    />
                    <div className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-xs pointer-events-none">
                      🔍
                    </div>
                    {memberSearchQuery && (
                      <button
                        type="button"
                        onClick={() => setMemberSearchQuery("")}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>

                <div className="border border-border/60 bg-card rounded-xl overflow-hidden overflow-x-auto shadow-xs">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-muted-foreground uppercase bg-muted/40 border-b border-border/60">
                      <tr>
                        <th className="px-5 py-4 font-semibold">User</th>
                        <th className="px-5 py-4 font-semibold">Role</th>
                        <th className="px-5 py-4 font-semibold">Status</th>
                        <th className="px-5 py-4 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {filteredMembers.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                            No team members found matching "{memberSearchQuery}".
                          </td>
                        </tr>
                      ) : (
                        filteredMembers.map((member) => {
                        const isOwner = member.role === "owner";
                        const isActing = actingOn === member.user_id;
                        const isSelf = user?.id === member.user_id;
                        const canChangeRole = !(isOwner && ownerCount === 1);
                        const isConfirming = confirmRemoveId === member.user_id;
                        
                        return (
                          <tr 
                            key={member.user_id} 
                            className={`group relative transition-colors ${isOwner ? "bg-primary/[0.02]" : "hover:bg-muted/30"}`}
                          >
                            <td className="px-5 py-4 relative">
                              <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-primary opacity-0 group-hover:opacity-100 transition-opacity" />
                              <div className="flex items-center gap-3">
                                <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs shadow-sm border
                                  ${isOwner ? "bg-primary/10 text-primary border-primary/20" : 
                                    member.role === 'admin' ? "bg-primary/10 text-primary border-primary/20" : 
                                    "bg-primary/10 text-primary border-primary/20"}`}
                                >
                                  {member.display_name?.charAt(0).toUpperCase()}
                                </div>
                                <div className="flex flex-col">
                                  <span className="font-medium text-foreground flex items-center gap-2">
                                    {member.display_name}
                                    {isSelf && <span className="text-[10px] uppercase bg-muted px-1.5 py-0.5 rounded text-muted-foreground">You</span>}
                                  </span>
                                  <span className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                    <Clock size={10} /> Joined {member.created_at ? format(new Date(member.created_at), 'MMM d, yyyy') : 'Unknown'}
                                  </span>
                                </div>
                              </div>
                            </td>
                            
                            <td className="px-5 py-4 relative">
                              {isActing ? (
                                <div className="flex items-center gap-2 text-muted-foreground text-xs">
                                  <Loader2 size={14} className="animate-spin" /> Updating...
                                </div>
                              ) : (
                                <div data-role-dropdown={member.user_id} className="relative inline-block">
                                  <button
                                    type="button"
                                    disabled={!canChangeRole}
                                    onClick={() => setOpenRoleDropdown(openRoleDropdown === member.user_id ? null : member.user_id)}
                                    className={`flex items-center gap-1.5 hover:opacity-80 transition-opacity ${!canChangeRole ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
                                    title={!canChangeRole ? "A workspace must have at least one owner." : "Change role"}
                                  >
                                    <RoleBadge role={member.role} />
                                    {canChangeRole && <ChevronDown size={14} className="text-muted-foreground" />}
                                  </button>
                                  
                                  <AnimatePresence>
                                    {openRoleDropdown === member.user_id && canChangeRole && (
                                      <motion.div
                                        initial={{ opacity: 0, y: -5, scale: 0.95 }}
                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                        exit={{ opacity: 0, y: -5, scale: 0.95 }}
                                        transition={{ duration: 0.15 }}
                                        className="absolute top-full left-0 mt-2 w-64 bg-popover border border-border rounded-lg shadow-xl z-50 overflow-hidden"
                                      >
                                        <div className="flex flex-col p-1">
                                          {(["member", "admin", "owner"] as const).map((r) => (
                                            <button
                                              type="button"
                                              key={r}
                                              onClick={() => {
                                                if (r !== member.role && !isPro) {
                                                  openPaywall({ featureName: "Role-Based Permissions & Delegation" });
                                                  return;
                                                }
                                                handleRoleChange(member.user_id, r);
                                              }}
                                              className={`flex items-start gap-3 px-3 py-2 text-xs text-left rounded-md hover:bg-muted/60 transition-colors ${member.role === r ? 'bg-muted font-medium' : 'text-muted-foreground'}`}
                                            >
                                              <div className="pt-0.5">
                                                {r === 'owner' && <Crown size={14} className="text-primary" />}
                                                {r === 'admin' && <Shield size={14} className="text-primary" />}
                                                {r === 'member' && <UserIcon size={14} />}
                                              </div>
                                              <div className="flex flex-col">
                                                <span className="capitalize text-foreground flex items-center gap-1.5">
                                                  <span>{r}</span>
                                                  {!isPro && r !== "member" && <Lock size={10} className="text-amber-500 shrink-0" />}
                                                </span>
                                                <span className="text-[10px] text-muted-foreground">{ROLE_SUBTITLES[r]?.subtitle || ""}</span>
                                              </div>
                                              {member.role === r && <Check size={14} className="ml-auto mt-0.5 text-primary" />}
                                            </button>
                                          ))}
                                        </div>
                                      </motion.div>
                                    )}
                                  </AnimatePresence>
                                </div>
                              )}
                            </td>
                            
                            <td className="px-5 py-4">
                              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/10 text-success border border-success/20">
                                <span className="w-1.5 h-1.5 rounded-full bg-success"></span>
                                Active
                              </span>
                            </td>
                            
                            <td className="px-5 py-4 text-right">
                              <div className="flex justify-end items-center gap-1 relative h-8">
                                <button
                                  type="button"
                                  onClick={() => openPermissionsModal(member)}
                                  className="text-muted-foreground hover:text-foreground p-2 rounded-md hover:bg-muted transition-colors cursor-pointer"
                                  title="Configure granular permissions"
                                >
                                  <Sliders size={15} />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => initiateRemoval(member.user_id)}
                                  disabled={isActing || isSelf}
                                  className="text-muted-foreground hover:text-destructive p-2 rounded-md hover:bg-destructive/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed group/btn cursor-pointer"
                                  title={isSelf ? "You cannot remove yourself" : "Remove member"}
                                >
                                  <Trash2 size={16} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      }))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Pending Invites Table */}
            {invites.length > 0 && (
              <div>
                <h3 className="text-lg font-bold tracking-tight text-foreground mb-4 pl-1">Pending Invites</h3>
                <div className="border border-border/60 bg-card rounded-xl overflow-hidden overflow-x-auto shadow-xs">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-muted-foreground uppercase bg-muted/40 border-b border-border/60">
                      <tr>
                        <th className="px-5 py-4 font-semibold">User</th>
                        <th className="px-5 py-4 font-semibold">Role</th>
                        <th className="px-5 py-4 font-semibold">Status</th>
                        <th className="px-5 py-4 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {invites.map((invite) => (
                        <tr key={invite.id} className="group transition-colors hover:bg-muted/30">
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-full border border-dashed border-muted-foreground/40 bg-muted/20 text-muted-foreground flex items-center justify-center font-bold text-xs">
                                {invite.email.charAt(0).toUpperCase()}
                              </div>
                              <div className="flex flex-col">
                                <span className="font-medium text-foreground">{invite.email}</span>
                                <span className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                  <Clock size={10} /> Sent {format(new Date(invite.created_at), 'MMM d, yyyy')}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            <RoleBadge role={invite.role} />
                          </td>
                          <td className="px-5 py-4">
                            {(() => {
                              const createdMs = invite.created_at ? new Date(invite.created_at).getTime() : Date.now();
                              const daysSince = Math.floor((Date.now() - createdMs) / (1000 * 60 * 60 * 24));
                              const remaining = Math.max(0, 7 - daysSince);
                              return (
                                <div className="flex flex-col gap-1 items-start">
                                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20">
                                    <span className="relative flex h-1.5 w-1.5">
                                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary"></span>
                                    </span>
                                    Pending
                                  </span>
                                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                    remaining === 0 
                                      ? "bg-rose-500/10 text-rose-500 border border-rose-500/20" 
                                      : remaining <= 2 
                                        ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" 
                                        : "bg-muted text-muted-foreground border border-border"
                                  }`}>
                                    {remaining === 0 ? "Expired" : `Expires in ${remaining}d`}
                                  </span>
                                </div>
                              );
                            })()}
                          </td>
                          <td className="px-5 py-4 text-right">
                            <div className="flex items-center gap-2 justify-end">
                              <button
                                type="button"
                                onClick={() => handleResendInvite(invite.id, invite.email)}
                                disabled={resendingInviteId === invite.id || (resendCooldowns[invite.id] ?? 0) > 0}
                                className="text-foreground hover:text-primary font-medium text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-2xs"
                                title="Resend invitation email"
                              >
                                {resendingInviteId === invite.id ? (
                                  <Loader2 size={12} className="animate-spin" />
                                ) : (
                                  <RotateCcw size={12} />
                                )}
                                <span>
                                  {(resendCooldowns[invite.id] ?? 0) > 0
                                    ? `Resend (${resendCooldowns[invite.id]}s)`
                                    : "Resend Invite"}
                                </span>
                              </button>
                              {invite.token && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    const fullUrl = `${window.location.origin}/accept-invite?token=${invite.token}`;
                                    navigator.clipboard.writeText(fullUrl);
                                    toast.success(`Invite link for ${invite.email} copied to clipboard!`);
                                  }}
                                  className="text-primary hover:text-primary/80 font-medium text-xs px-2.5 py-1.5 rounded-lg border border-primary/20 hover:bg-primary/10 transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
                                  title="Copy invite URL to clipboard"
                                >
                                  <Copy size={12} />
                                  <span>Copy Link</span>
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleRevokeInvite(invite.id, invite.email)}
                                disabled={revokingId === invite.id}
                                className="text-destructive hover:text-destructive/80 font-medium text-xs px-2.5 py-1.5 rounded-lg border border-destructive/20 hover:bg-destructive/10 transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                                title="Revoke this pending invitation"
                              >
                                {revokingId === invite.id ? (
                                  <Loader2 size={12} className="animate-spin" />
                                ) : (
                                  <Trash2 size={12} />
                                )}
                                <span>Revoke</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Modal for Removal Confirmation (WCAG 2.2 Accessible Dialog) */}
            <AnimatePresence>
              {confirmRemoveId && (
                <div 
                  className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-xs p-4"
                  onClick={(e) => {
                    if (e.target === e.currentTarget) cancelRemoval();
                  }}
                >
                  <motion.div 
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="confirm-remove-title"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="bg-card border border-border rounded-xl shadow-2xl p-6 max-w-sm w-full"
                  >
                    <h3 id="confirm-remove-title" className="text-lg font-bold text-foreground mb-2 flex items-center gap-2">
                      <AlertTriangle className="text-destructive" size={20} />
                      Confirm Removal
                    </h3>
                    <p className="text-sm text-muted-foreground mb-6">
                      Are you sure you want to remove {members.find(m => m.user_id === confirmRemoveId)?.display_name} from the workspace? They will immediately lose access to all campaigns and data.
                    </p>
                    <div className="flex justify-end gap-3">
                      <button 
                        type="button"
                        onClick={cancelRemoval}
                        className="px-4 py-2 text-sm font-medium rounded-lg hover:bg-muted transition-colors cursor-pointer text-foreground"
                      >
                        Cancel
                      </button>
                      <button 
                        type="button"
                        onClick={() => {
                          const member = members.find(m => m.user_id === confirmRemoveId);
                          if (member) handleRemove(member.user_id, member.display_name);
                        }}
                        className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors cursor-pointer shadow-sm"
                      >
                        Remove
                      </button>
                    </div>
                  </motion.div>
                </div>
              )}
            </AnimatePresence>

            {/* Modal for Granular Permissions */}
            <AnimatePresence>
              {permissionModalMember && (
                <div
                  className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-xs p-4"
                  onClick={(e) => {
                    if (e.target === e.currentTarget && !savingPermissions) {
                      setPermissionModalMember(null);
                    }
                  }}
                >
                  <motion.div
                    role="dialog"
                    aria-modal="true"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="bg-card border border-border rounded-2xl shadow-2xl p-6 max-w-md w-full space-y-5"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-border">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 rounded-lg bg-primary/10 text-primary">
                          <Sliders size={18} />
                        </div>
                        <div>
                          <h3 className="text-base font-bold text-foreground">
                            Granular Access Rights
                          </h3>
                          <p className="text-xs text-muted-foreground">
                            Member: {permissionModalMember.display_name} ({permissionModalMember.role})
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setPermissionModalMember(null)}
                        className="text-muted-foreground hover:text-foreground cursor-pointer"
                      >
                        <X size={18} />
                      </button>
                    </div>

                    <div className="space-y-3">
                      <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-muted/20 hover:bg-muted/40 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={memberPermissions.can_export_leads}
                          onChange={(e) => setMemberPermissions({ ...memberPermissions, can_export_leads: e.target.checked })}
                          className="mt-1 rounded border-border text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-bold text-foreground block">Export & Download Prospects</span>
                          <span className="text-[11px] text-muted-foreground leading-normal">
                            Allow downloading lead lists, enriched emails, and campaign CSV exports.
                          </span>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-muted/20 hover:bg-muted/40 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={memberPermissions.can_delete_campaigns}
                          onChange={(e) => setMemberPermissions({ ...memberPermissions, can_delete_campaigns: e.target.checked })}
                          className="mt-1 rounded border-border text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-bold text-foreground block">Delete Campaigns & Sequences</span>
                          <span className="text-[11px] text-muted-foreground leading-normal">
                            Allow permanently deleting live campaigns, sequences, and lead execution history.
                          </span>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-muted/20 hover:bg-muted/40 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={memberPermissions.can_connect_accounts}
                          onChange={(e) => setMemberPermissions({ ...memberPermissions, can_connect_accounts: e.target.checked })}
                          className="mt-1 rounded border-border text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-bold text-foreground block">Connect Senders & Mailboxes</span>
                          <span className="text-[11px] text-muted-foreground leading-normal">
                            Allow linking new LinkedIn accounts and SMTP/IMAP outreach sending inboxes.
                          </span>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-muted/20 hover:bg-muted/40 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={memberPermissions.can_manage_billing}
                          onChange={(e) => setMemberPermissions({ ...memberPermissions, can_manage_billing: e.target.checked })}
                          className="mt-1 rounded border-border text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-bold text-foreground block">Manage Billing & Seats</span>
                          <span className="text-[11px] text-muted-foreground leading-normal">
                            Allow upgrading subscription tiers, adding paid seats, and viewing payment invoices.
                          </span>
                        </div>
                      </label>
                    </div>

                    <div className="pt-2 flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setPermissionModalMember(null)}
                        className="px-4 py-2 bg-muted text-muted-foreground text-xs font-semibold rounded-xl hover:bg-muted/80 hover:text-foreground cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={handleSavePermissions}
                        disabled={savingPermissions}
                        className="px-5 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 cursor-pointer flex items-center gap-1.5"
                      >
                        {savingPermissions ? <Loader2 size={13} className="animate-spin" /> : null}
                        Save Privileges
                      </button>
                    </div>
                  </motion.div>
                </div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
