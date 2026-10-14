import { useState, useRef, useEffect } from "react";
import { 
  Users, UserPlus, Loader2, ChevronDown, Check, X, 
  Shield, Mail, Crown, User as UserIcon, Trash2, AlertTriangle, Clock,
  Zap, ArrowRight, Lock, Copy
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

type Role = "owner" | "admin" | "member";

interface Member {
  user_id: string;
  role: Role;
  display_name: string;
  created_at: string;
}

interface Invite {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  status: string;
}

export function TeamSettings({ workspaceId }: { workspaceId: string | null }) {
  const { user } = useAuth();
  const { openPaywall } = usePaywall();
  const { data, mutate, isLoading, error } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/members` : null,
    fetcher
  );

  const { data: billingData } = useSWR<{ tier?: string }>(
    workspaceId ? '/api/elein/workspaces/billing' : null,
    fetcher
  );
  const tier = billingData?.tier || 'FREE';
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE';
  const maxSeats = isPro ? (tier === 'ENTERPRISE' ? 25 : 5) : 1;
  
  const members: Member[] = data?.members || [];
  const invites: Invite[] = data?.invites || [];
  const totalPeople = members.length + invites.length;
  const isSeatCapped = totalPeople >= maxSeats;

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
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

  // Close dropdowns on outside click
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpenRoleDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const handleInviteToggle = () => {
    if (!isPro && isSeatCapped) {
      openPaywall({ featureName: "Team Members & Seats" });
      toast.info("Free plan is limited to 1 member. Upgrade to Growth Pro to invite team members.");
      return;
    }
    setShowInviteForm(!showInviteForm);
  };

  const handleInvite = async () => {
    if (isSubmittingRef.current || !inviteEmail.trim() || !workspaceId) return;
    
    // Paranoia Layer 1 & 2: Seat Cap check
    if (!isPro && isSeatCapped) {
      openPaywall({ featureName: "Team Members & Seats" });
      toast.info("Free plan seat limit reached (1/1). Upgrade to Growth Pro to invite team members.");
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
      const res = await fetchWithAuth(
        `/api/workspaces/${workspaceId}/members/${targetUserId}/role`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role: newRole }),
        }
      );
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update role");
      }
      toast.success("Role updated successfully");
      mutate();
    } catch (e: any) {
      friendlyToast('Failed to update role — please try again.', e);
    } finally {
      setActingOn(null);
    }
  };

  const initiateRemoval = (userId: string) => {
    setConfirmRemoveId(userId);
  };

  const cancelRemoval = () => {
    setConfirmRemoveId(null);
  };

  const handleRemove = async (targetUserId: string, displayName: string) => {
    if (!workspaceId) return;
    cancelRemoval();
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
      <div className="p-6 rounded-[24px] border border-destructive/20 bg-destructive/5 shadow-sm">
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

  const ownerCount = members.filter(m => m.role === "owner").length;

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
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
            <Shield size={12} />
            Admin
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100/50 text-gray-500 border border-gray-200">
            <UserIcon size={12} />
            Member
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <div className="p-6 md:p-8 rounded-[24px] border border-border bg-card relative overflow-hidden shadow-sm">
        <div className="absolute top-0 left-0 w-1 h-full bg-primary/40 rounded-l-2xl"></div>
        
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
            onClick={handleInviteToggle}
            className={`flex items-center gap-2 px-5 py-2.5 font-semibold text-sm rounded-lg transition-all shadow-md active:scale-95 ${
              !isPro && isSeatCapped
                ? "bg-muted text-foreground hover:bg-muted/80 border border-border"
                : "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground hover:opacity-90"
            }`}
          >
            {showInviteForm ? (
              <X size={16} />
            ) : !isPro && isSeatCapped ? (
              <Lock size={15} className="text-amber-500" />
            ) : (
              <UserPlus size={16} />
            )}
            {showInviteForm ? "Close" : !isPro && isSeatCapped ? "Upgrade to Add Members" : "Invite Member"}
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
              onClick={() => {
                navigator.clipboard.writeText(createdInviteLink);
                setCopiedLink(true);
                toast.success("Invite link copied to clipboard!");
                setTimeout(() => setCopiedLink(false), 2000);
              }}
              className="px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold flex items-center gap-1.5 hover:bg-primary/90 transition-all shrink-0 cursor-pointer shadow-sm active:scale-95"
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
              onClick={() => openPaywall({ featureName: "Team Members & Seats" })}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all shadow-sm shrink-0 whitespace-nowrap active:scale-95"
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
              <div className="mb-8 p-6 bg-gray-100/20 border border-gray-200 rounded-xl shadow-inner relative">
                {/* Zeigarnik effect progress indicator */}
                {inviteEmail.length > 0 && (
                  <div className="absolute top-0 left-0 h-1 bg-primary/30 w-full rounded-t-xl overflow-hidden">
                    <div 
                      className="h-full bg-primary transition-all duration-300 ease-out"
                      style={{ width: `${Math.min((inviteEmail.length / 15) * 100, 100)}%` }}
                    />
                  </div>
                )}
                
                <div className="flex flex-col sm:flex-row gap-5 items-end">
                  <div className="flex-1 w-full space-y-2">
                    <label className="text-sm font-semibold text-gray-900/80">Email Address</label>
                    <div className="relative group">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-primary transition-colors" size={16} />
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        placeholder="colleague@company.com"
                        className="w-full bg-background border border-gray-200/80 rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 transition-all placeholder:text-gray-500/50"
                      />
                    </div>
                  </div>
                  
                  <div className="w-full sm:w-48 space-y-2">
                    <label className="text-sm font-semibold text-gray-900/80">Role</label>
                    <div className="relative">
                      <Shield className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
                      <select
                        value={inviteRole}
                        onChange={(e) => {
                          const val = e.target.value as Role;
                          if (val !== "member" && !isPro) {
                            openPaywall({ featureName: "Role-Based Permissions & Delegation" });
                            return;
                          }
                          setInviteRole(val);
                        }}
                        className="w-full bg-background border border-gray-200/80 rounded-lg pl-10 pr-8 py-2.5 text-sm appearance-none focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 transition-all cursor-pointer"
                      >
                        <option value="member">Member</option>
                        <option value="admin">{isPro ? "Admin" : "Admin (Growth Pro)"}</option>
                        <option value="owner">{isPro ? "Owner" : "Owner (Growth Pro)"}</option>
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" size={16} />
                    </div>
                  </div>
                  
                  <button
                    onClick={handleInvite}
                    disabled={sending || !inviteEmail.trim()}
                    className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-2.5 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm active:scale-95"
                  >
                    {sending ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                    Send Invite
                  </button>
                </div>
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
                <h3 className="text-lg font-bold tracking-tight text-gray-900 mb-4 pl-1">Active Members</h3>
                <div className="border border-gray-200/50 bg-background/50 rounded-xl overflow-hidden overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-100/30 border-b border-gray-200/50">
                      <tr>
                        <th className="px-5 py-4 font-semibold">User</th>
                        <th className="px-5 py-4 font-semibold">Role</th>
                        <th className="px-5 py-4 font-semibold">Status</th>
                        <th className="px-5 py-4 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {members.map((member) => {
                        const isOwner = member.role === "owner";
                        const isActing = actingOn === member.user_id;
                        const isSelf = user?.id === member.user_id;
                        const canChangeRole = !(isOwner && ownerCount === 1);
                        const isConfirming = confirmRemoveId === member.user_id;
                        
                        return (
                          <tr 
                            key={member.user_id} 
                            className={`group relative transition-colors ${isOwner ? "bg-primary/[0.02]" : "hover:bg-gray-100/10"}`}
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
                                  <span className="font-medium text-gray-900 flex items-center gap-2">
                                    {member.display_name}
                                    {isSelf && <span className="text-[10px] uppercase bg-gray-100 px-1.5 py-0.5 rounded text-gray-500">You</span>}
                                  </span>
                                  <span className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                                    <Clock size={10} /> Joined {member.created_at ? format(new Date(member.created_at), 'MMM d, yyyy') : 'Unknown'}
                                  </span>
                                </div>
                              </div>
                            </td>
                            
                            <td className="px-5 py-4 relative">
                              {isActing ? (
                                <div className="flex items-center gap-2 text-gray-500 text-xs">
                                  <Loader2 size={14} className="animate-spin" /> Updating...
                                </div>
                              ) : (
                                <div ref={dropdownRef} className="relative inline-block">
                                  <button
                                    disabled={!canChangeRole}
                                    onClick={() => setOpenRoleDropdown(openRoleDropdown === member.user_id ? null : member.user_id)}
                                    className={`flex items-center gap-1.5 hover:opacity-80 transition-opacity ${!canChangeRole ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
                                    title={!canChangeRole ? "A workspace must have at least one owner." : "Change role"}
                                  >
                                    <RoleBadge role={member.role} />
                                    {canChangeRole && <ChevronDown size={14} className="text-gray-500" />}
                                  </button>
                                  
                                  <AnimatePresence>
                                    {openRoleDropdown === member.user_id && canChangeRole && (
                                      <motion.div
                                        initial={{ opacity: 0, y: -5, scale: 0.95 }}
                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                        exit={{ opacity: 0, y: -5, scale: 0.95 }}
                                        transition={{ duration: 0.15 }}
                                        className="absolute top-full left-0 mt-2 w-64 bg-surface border border-gray-200 rounded-lg shadow-xl z-50 overflow-hidden"
                                      >
                                        <div className="flex flex-col p-1">
                                          {(["member", "admin", "owner"] as Role[]).map((r) => {
                                            const roleDetails = {
                                              owner: { subtitle: "Full access and billing" },
                                              admin: { subtitle: "Can edit settings" },
                                              member: { subtitle: "View only access" }
                                            };
                                            return (
                                            <button
                                              key={r}
                                              onClick={() => {
                                                if (r !== member.role && !isPro) {
                                                  openPaywall({ featureName: "Role-Based Permissions & Delegation" });
                                                  return;
                                                }
                                                handleRoleChange(member.user_id, r);
                                              }}
                                              className={`flex items-start gap-3 px-3 py-2 text-xs text-left rounded-md hover:bg-gray-100/50 transition-colors ${member.role === r ? 'bg-gray-100/30 font-medium' : 'text-gray-500'}`}
                                            >
                                              <div className="pt-0.5">
                                                {r === 'owner' && <Crown size={14} className="text-primary" />}
                                                {r === 'admin' && <Shield size={14} className="text-primary" />}
                                                {r === 'member' && <UserIcon size={14} />}
                                              </div>
                                              <div className="flex flex-col">
                                                <span className="capitalize text-gray-900 flex items-center gap-1.5">
                                                  <span>{r}</span>
                                                  {!isPro && r !== "member" && <Lock size={10} className="text-amber-500 shrink-0" />}
                                                </span>
                                                <span className="text-[10px] text-gray-500">{roleDetails[r].subtitle}</span>
                                              </div>
                                              {member.role === r && <Check size={14} className="ml-auto mt-0.5" />}
                                            </button>
                                          )})}
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
                              <div className="flex justify-end items-center relative h-8">
                                <button
                                  onClick={() => initiateRemoval(member.user_id)}
                                  disabled={isActing || isSelf}
                                  className="text-gray-500 hover:text-destructive p-2 rounded-md hover:bg-destructive/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed group/btn"
                                  title={isSelf ? "You cannot remove yourself" : "Remove member"}
                                >
                                  <Trash2 size={16} className="group-hover/btn:scale-110 transition-transform" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Pending Invites Table */}
            {invites.length > 0 && (
              <div>
                <h3 className="text-lg font-bold tracking-tight text-gray-900 mb-4 pl-1">Pending Invites</h3>
                <div className="border border-gray-200/50 bg-background/50 rounded-xl overflow-hidden overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-100/30 border-b border-gray-200/50">
                      <tr>
                        <th className="px-5 py-4 font-semibold">User</th>
                        <th className="px-5 py-4 font-semibold">Role</th>
                        <th className="px-5 py-4 font-semibold">Status</th>
                        <th className="px-5 py-4 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {invites.map((invite) => (
                        <tr key={invite.id} className="group transition-colors hover:bg-gray-100/30">
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-full border border-dashed border-muted-foreground/40 bg-gray-100/10 text-gray-500 flex items-center justify-center font-bold text-xs">
                                {invite.email.charAt(0).toUpperCase()}
                              </div>
                              <div className="flex flex-col">
                                <span className="font-medium text-gray-900">{invite.email}</span>
                                <span className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                                  <Clock size={10} /> Sent {format(new Date(invite.created_at), 'MMM d, yyyy')}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            <RoleBadge role={invite.role} />
                          </td>
                          <td className="px-5 py-4">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20">
                              <span className="relative flex h-1.5 w-1.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary"></span>
                              </span>
                              Pending
                            </span>
                          </td>
                          <td className="px-5 py-4 text-right">
                            <div className="flex items-center gap-2 justify-end">
                              <button
                                onClick={() => handleRevokeInvite(invite.id, invite.email)}
                                disabled={revokingId === invite.id}
                                className="text-destructive hover:text-destructive/80 font-medium text-xs px-2.5 py-1.5 rounded-lg border border-destructive/20 hover:bg-destructive/10 transition-all flex items-center gap-1.5 active:scale-95 disabled:opacity-50 cursor-pointer"
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

            {/* Modal for Removal Confirmation */}
            <AnimatePresence>
              {confirmRemoveId && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4">
                  <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="bg-surface border border-gray-200 rounded-xl shadow-2xl p-6 max-w-sm w-full"
                  >
                    <h3 className="text-lg font-bold text-gray-900 mb-2 flex items-center gap-2">
                      <AlertTriangle className="text-destructive" size={20} />
                      Confirm Removal
                    </h3>
                    <p className="text-sm text-gray-500 mb-6">
                      Are you sure you want to remove {members.find(m => m.user_id === confirmRemoveId)?.display_name} from the workspace? They will immediately lose access to all campaigns and data.
                    </p>
                    <div className="flex justify-end gap-3">
                      <button 
                        onClick={cancelRemoval}
                        className="px-4 py-2 text-sm font-medium rounded-lg hover:bg-gray-100 transition-colors"
                      >
                        Cancel
                      </button>
                      <button 
                        onClick={() => {
                          const member = members.find(m => m.user_id === confirmRemoveId);
                          if (member) handleRemove(member.user_id, member.display_name);
                        }}
                        className="px-4 py-2 text-sm font-medium bg-destructive text-white rounded-lg hover:bg-destructive/90 transition-colors"
                      >
                        Remove
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
