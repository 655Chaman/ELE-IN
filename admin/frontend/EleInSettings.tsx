import { motion, AnimatePresence } from "motion/react";
import {
  Users,
  Building2,
  Send,
  Ban,
  Bell,
  Shield,
  Activity,
  AlertTriangle,
  Settings2,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { EmptyState } from "@/components/EmptyState";

// Import the modularized Settings components
import { TeamSettings } from "@/pages/settings/TeamSettings";
import { WorkspaceProfile } from "@/pages/settings/WorkspaceProfile";
import { SendingDefaults } from "@/pages/settings/SendingDefaults";
import { ExclusionsSettings } from "@/pages/settings/ExclusionsSettings";
import { NotificationSettings } from "@/pages/settings/NotificationSettings";
import { SecuritySettings } from "@/pages/settings/SecuritySettings";
import { AuditLogSettings } from "@/pages/settings/AuditLogSettings";
import { DangerZone } from "@/pages/settings/DangerZone";

export function EleInSettings() {
  const { activeWorkspaceId } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();

  const validTabs = ["team", "profile", "sending", "exclusions", "notifications", "security", "audit", "danger"];
  const tabParam = searchParams.get("tab");
  const activeTab = validTabs.includes(tabParam || "") ? (tabParam as string) : "team";

  const handleTabChange = (newTab: string) => {
    setSearchParams({ tab: newTab });
  };

  const handleKeyDown = (e: React.KeyboardEvent, currentIndex: number) => {
    let nextIndex = currentIndex;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % tabs.length;
    } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === "Home") {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === "End") {
      e.preventDefault();
      nextIndex = tabs.length - 1;
    } else {
      return;
    }
    const nextTab = tabs[nextIndex];
    handleTabChange(nextTab.id);
    document.getElementById(`settings-tab-${nextTab.id}`)?.focus();
  };

  const tabs = [
    { id: "team", label: "Team & Access", icon: Users },
    { id: "profile", label: "Workspace Profile", icon: Building2 },
    { id: "sending", label: "Sending Defaults", icon: Send },
    { id: "exclusions", label: "Exclusions & DNC", icon: Ban },
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "security", label: "Security", icon: Shield },
    { id: "audit", label: "Audit Log", icon: Activity },
    { id: "danger", label: "Danger Zone", icon: AlertTriangle },
  ];

  if (!activeWorkspaceId) {
    return (
      <div className="max-w-[1240px] mx-auto p-6 sm:p-8 font-sans">
        <EmptyState
          title="No Workspace Selected"
          description="Please select or create an active workspace from the top navigation to view and manage settings."
          icon={Building2}
        />
      </div>
    );
  }

  return (
    <div className="max-w-[1240px] mx-auto p-6 sm:p-8 font-sans">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-foreground mb-1 flex items-center gap-2">
          <Settings2 size={20} className="text-primary" />
          <span>Workspace Settings</span>
        </h1>
        <p className="text-xs text-muted-foreground">Manage your workspace configuration, team access, and safety defaults.</p>
      </div>

      <div className="flex flex-col md:flex-row gap-8">
        {/* Left Sub-Nav with WCAG 2.2 Tablist ARIA semantics */}
        <div
          role="tablist"
          aria-label="Workspace Settings Sections"
          className="w-full md:w-64 shrink-0 flex flex-col gap-1"
        >
          {tabs.map((tab, idx) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const isDanger = tab.id === "danger";
            return (
              <button
                key={tab.id}
                id={`settings-tab-${tab.id}`}
                role="tab"
                type="button"
                aria-selected={isActive}
                aria-controls={`settings-tabpanel-${tab.id}`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => handleTabChange(tab.id)}
                onKeyDown={(e) => handleKeyDown(e, idx)}
                className={`relative flex items-center gap-3 px-4 py-2.5 text-xs font-semibold rounded-xl transition-colors cursor-pointer text-left ${
                  isActive
                    ? isDanger
                      ? "text-destructive"
                      : "text-primary-foreground font-bold"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="settings-active-pill"
                    className={`absolute inset-0 rounded-xl ${
                      isDanger
                        ? "bg-destructive/15 border border-destructive/30"
                        : "bg-primary shadow-sm"
                    }`}
                    transition={{ type: "spring", stiffness: 450, damping: 32 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-3">
                  <Icon size={16} />
                  <span>{tab.label}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Content Area with Accessible Tabpanel */}
        <div
          id={`settings-tabpanel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`settings-tab-${activeTab}`}
          className="flex-1 min-w-0"
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              {activeTab === "team" && <TeamSettings workspaceId={activeWorkspaceId} />}
              {activeTab === "profile" && <WorkspaceProfile workspaceId={activeWorkspaceId} />}
              {activeTab === "sending" && <SendingDefaults workspaceId={activeWorkspaceId} />}
              {activeTab === "exclusions" && <ExclusionsSettings workspaceId={activeWorkspaceId} />}
              {activeTab === "notifications" && <NotificationSettings workspaceId={activeWorkspaceId} />}
              {activeTab === "security" && <SecuritySettings workspaceId={activeWorkspaceId} />}
              {activeTab === "audit" && <AuditLogSettings workspaceId={activeWorkspaceId} />}
              {activeTab === "danger" && <DangerZone workspaceId={activeWorkspaceId} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
