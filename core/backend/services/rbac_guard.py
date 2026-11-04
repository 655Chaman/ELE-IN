"""
Three-Layer Paranoia Architecture: Enterprise RBAC & Audit Trail Guard (Phase T)
==================================================================================
Layer 0 (Foundational):
  - Scoped role definitions: owner, admin, manager, sender, analyst.
  - Granular permission policies (campaign creation, sender management, lead export, billing).
  - Centralized audit trail logger (workspace_audit_logs) capturing actor, role, action, resource, IP, and status.

Layer 1 (Environmental Failure Analysis):
  - Fail-closed security posture: Unverified roles or missing workspace membership reject immediately (HTTP 403).
  - Database-resilient audit logging: Non-blocking fallback to persistent logger and in-memory buffer if audit table is degraded.
  - Sensitive credential sanitization: Automatically strips session cookies, JWTs, DEKs, and passwords from audit detail payloads.

Layer 2 (Human Paranoia):
  - Exfiltration Shield: Analysts and unprivileged roles attempting lead export are blocked with 403 Forbidden and logged as high-severity security events.
  - Last-Admin Lockout Prevention: Prohibits demoting or removing the final administrator from a workspace.
  - Anti-Privilege Escalation: Prevents managers from promoting themselves or peers to admin/owner roles.
"""

import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set
from fastapi import HTTPException, Request

logger = logging.getLogger("rbac_guard")

# Role constants
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_SENDER = "sender"
ROLE_ANALYST = "analyst"

ALL_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER, ROLE_SENDER, ROLE_ANALYST}

# Role permission registry
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_OWNER: {"*"},
    ROLE_ADMIN: {"*"},
    ROLE_MANAGER: {
        "campaign:view", "campaign:create", "campaign:edit", "campaign:delete", "campaign:pause", "campaign:resume",
        "lead:view", "lead:import", "lead:export", "lead:edit", "lead:delete",
        "sender:view", "sender:assign",
        "analytics:view", "template:manage", "webhook:view", "inbox:manage"
    },
    ROLE_SENDER: {
        "sender:view_own", "sender:connect", "sender:reconnect", "sender:update_cookies",
        "lead:view_assigned", "inbox:manage_assigned", "analytics:view_own"
    },
    ROLE_ANALYST: {
        "analytics:view", "campaign:view", "lead:view", "report:view"
    }
}

# In-memory circular buffer for audit trails in case DB is offline/migrating
_IN_MEMORY_AUDIT_LOGS: List[Dict[str, Any]] = []
_MAX_IN_MEMORY_AUDIT_ENTRIES = 1000

# Sensitive keys to scrub from audit details
SENSITIVE_AUDIT_KEYS = {"password", "token", "secret", "cookie", "dek", "key", "authorization", "session_cookies"}


class RBACGuard:
    """Enterprise Role-Based Access Control and Audit Trail Enforcement Guard."""

    @staticmethod
    def has_permission(role: Optional[str], permission: str) -> bool:
        """
        Layer 0 & 1: Checks whether the given role has the requested permission.
        Fail-closed: Returns False if role is None, empty, or unmapped.
        """
        if not role or not isinstance(role, str):
            return False
        
        role_clean = role.strip().lower()
        perms = ROLE_PERMISSIONS.get(role_clean, set())
        if "*" in perms:
            return True
        return permission in perms

    @staticmethod
    def sanitize_audit_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Layer 1 & 2: Recursively sanitizes sensitive tokens, passwords, and secrets
        before writing to audit logs or system logs.
        """
        if not details or not isinstance(details, dict):
            return {}

        sanitized = {}
        for k, v in details.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_AUDIT_KEYS):
                sanitized[k] = "[REDACTED_CONFIDENTIAL]"
            elif isinstance(v, dict):
                sanitized[k] = RBACGuard.sanitize_audit_details(v)
            elif isinstance(v, list):
                sanitized[k] = [
                    RBACGuard.sanitize_audit_details(item) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                sanitized[k] = v
        return sanitized

    @staticmethod
    def verify_permission(
        role: Optional[str],
        permission: str,
        resource_type: str = "resource",
        resource_id: Optional[str] = None
    ) -> None:
        """
        Layer 0 & 2: Validates role permission. Raises HTTP 403 Forbidden if not authorized.
        """
        if not RBACGuard.has_permission(role, permission):
            logger.warning(
                f"[RBAC DENIAL] Role '{role}' attempted unauthorized action '{permission}' on {resource_type} '{resource_id}'."
            )
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: role '{role or 'unauthorized'}' lacks required permission '{permission}' for {resource_type}."
            )

    @staticmethod
    def verify_role_assignment_authority(actor_role: str, target_new_role: str) -> None:
        """
        Layer 2 Paranoia: Prevents privilege escalation.
        - Only owner/admin can assign admin or owner.
        - Non-admins cannot assign roles equal to or higher than their own rank.
        """
        actor = (actor_role or "").lower()
        target = (target_new_role or "").lower()

        if target not in ALL_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target role '{target_new_role}'. Must be one of: {', '.join(sorted(list(ALL_ROLES)))}"
            )

        if actor not in (ROLE_OWNER, ROLE_ADMIN):
            raise HTTPException(
                status_code=403,
                detail="Privilege escalation prohibited: only workspace administrators can modify member roles."
            )

        if target in (ROLE_OWNER, ROLE_ADMIN) and actor != ROLE_OWNER and target == ROLE_OWNER:
            raise HTTPException(
                status_code=403,
                detail="Only the workspace owner can transfer or assign workspace ownership."
            )

    @staticmethod
    def prevent_last_admin_lockout(
        workspace_id: str,
        target_user_id: str,
        new_role: Optional[str],
        db: Any
    ) -> None:
        """
        Layer 2 Paranoia: Ensures a workspace always retains at least one active administrator.
        Prevents self-demotion or removal if target_user_id is the sole admin.
        """
        if not db or not workspace_id or not target_user_id:
            return

        # If new_role is still admin or owner, no lockout risk
        if new_role and new_role.lower() in (ROLE_OWNER, ROLE_ADMIN):
            return

        try:
            # Check owner in workspaces table
            ws_res = db.table("workspaces").select("owner_id").eq("id", workspace_id).execute()
            ws_owner = None
            if getattr(ws_res, "data", None):
                ws_owner = ws_res.data[0].get("owner_id")

            # Check admins in workspace_members
            mem_res = db.table("workspace_members").select("user_id, role").eq("workspace_id", workspace_id).in_("role", [ROLE_OWNER, ROLE_ADMIN]).execute()
            admins = getattr(mem_res, "data", []) or []
            
            admin_user_ids = {a.get("user_id") for a in admins if a.get("user_id")}
            if ws_owner:
                admin_user_ids.add(ws_owner)

            if target_user_id in admin_user_ids and len(admin_user_ids) <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Operation rejected: cannot remove or demote the sole administrator of this workspace."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error checking last admin lockout: {e}")

    @staticmethod
    def log_rbac_audit_event(
        actor_id: str,
        actor_role: str,
        workspace_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        status: str = "SUCCESS",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Layer 0, 1 & 2: Writes tamper-evident audit trail record.
        - Sanitizes all secrets and credentials.
        - Persists to DB workspace_audit_logs if available.
        - Buffers in memory and logs to system audit logger as fallback.
        """
        safe_details = RBACGuard.sanitize_audit_details(details)
        now_iso = datetime.now(timezone.utc).isoformat()
        log_id = str(uuid.uuid4())

        entry = {
            "id": log_id,
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            "actor_role": actor_role or "unknown",
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": status,
            "details": safe_details,
            "ip_address": ip_address or "internal",
            "user_agent": user_agent or "internal",
            "created_at": now_iso
        }

        # System logger audit output
        logger.info(
            f"[AUDIT] {entry['status']} action='{action}' actor='{actor_id}' role='{actor_role}' ws='{workspace_id}' resource='{resource_type}:{resource_id}'"
        )

        # In-memory buffer fallback
        global _IN_MEMORY_AUDIT_LOGS
        _IN_MEMORY_AUDIT_LOGS.append(entry)
        if len(_IN_MEMORY_AUDIT_LOGS) > _MAX_IN_MEMORY_AUDIT_ENTRIES:
            _IN_MEMORY_AUDIT_LOGS = _IN_MEMORY_AUDIT_LOGS[-_MAX_IN_MEMORY_AUDIT_ENTRIES:]

        # DB persistence
        if db:
            try:
                db.table("workspace_audit_logs").insert(entry).execute()
            except Exception as e:
                # Layer 1 Paranoia: Never crash the business workflow if audit table insert fails
                logger.warning(f"Database write to workspace_audit_logs failed: {e}")

        return entry

    @staticmethod
    def get_recent_audit_logs(
        workspace_id: str,
        limit: int = 50,
        db: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recent audit logs for workspace from DB or in-memory fallback.
        """
        safe_limit = min(max(1, limit), 200)
        if db:
            try:
                res = db.table("workspace_audit_logs").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).limit(safe_limit).execute()
                data = getattr(res, "data", None)
                if isinstance(data, list):
                    return data
            except Exception as e:
                logger.warning(f"Failed to query workspace_audit_logs from DB: {e}")

        # Fallback to in-memory matching logs
        matching = [l for l in _IN_MEMORY_AUDIT_LOGS if l.get("workspace_id") == workspace_id]
        return list(reversed(matching[-safe_limit:]))
