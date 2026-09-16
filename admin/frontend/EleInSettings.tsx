import { motion, AnimatePresence } from "motion/react";
import {
  Users,
  Building2,
  Send,
  Bell,
  Shield,
  Activity,
  AlertTriangle,
  Settings2,
} from "lucide-react";
import ShinyText from "@/components/ShinyText";
import { useState } from "react";
import { useWorkspace } from "@/contexts/WorkspaceContext";

// Import the modularized Settings components
import { TeamSettings } from "@/pages/settings/TeamSettings";
import { WorkspaceProfile } from "@/pages/settings/WorkspaceProfile";
import { SendingDefaults } from "@/pages/settings/SendingDefaults";
import { NotificationSettings } from "@/pages/settings/NotificationSettings";
import { SecuritySettings } from "@/pages/settings/SecuritySettings";
import { AuditLogSettings } from "@/pages/settings/AuditLogSettings";
import { DangerZone } from "@/pages/settings/DangerZone";

export function EleInSettings() {
  const { activeWorkspaceId } = useWorkspace();
  const [activeTab, setActiveTab] = useState("team");

  const tabs = [
    { id: "team", label: "Team & Access", icon: Users },
    { id: "profile", label: "Workspace Profile", icon: Building2 },
    { id: "sending", label: "Sending Defaults", icon: Send },
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "security", label: "Security", icon: Shield },
    { id: "audit", label: "Audit Log", icon: Activity },
    { id: "danger", label: "Danger Zone", icon: AlertTriangle },
  ];

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-4 md:px-8 py-10 max-w-7xl mx-auto font-sans">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
          <Settings2 size={24} className="text-primary" />
          <ShinyText text="Workspace Settings" disabled={false} speed={3} className="" />
        </h1>
        <p className="text-sm text-muted-foreground">Manage your workspace configuration, team access, and safety defaults.</p>
      </motion.div>

      <div className="flex flex-col md:flex-row gap-8">
        {/* Left Sub-Nav */}
        <div className="w-full md:w-64 shrink-0 flex flex-col gap-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const isDanger = tab.id === "danger";
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-3 px-4 py-3 text-sm font-semibold rounded-xl transition-all ${
                  isActive
                    ? isDanger
                      ? "bg-destructive/10 text-destructive shadow-sm"
                      : "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon size={18} /> {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content Area */}
        <div className="flex-1 min-w-0">
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
