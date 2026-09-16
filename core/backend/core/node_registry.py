"""
Node Registry — the single source of truth for every node type available
in the workflow builder. Generic open-source style modules.
"""

from typing import Optional, Any

# ─────────────────────────────────────────────────────────────────────────────
# NODE_REGISTRY format:
#   key        → internal node type (used in DB + React Flow node.type)
#   label      → display name in palette
#   category   → palette grouping
#   icon       → lucide-react icon name (rendered on the frontend)
#   description→ one-liner shown under the node label in the palette
#   color      → legacy accent color class (ignored in minimal UI)
#   config_schema → list of config fields the user can fill in
#   outputs    → named output handles (for connecting to next nodes)
# ─────────────────────────────────────────────────────────────────────────────

NODE_REGISTRY: dict[str, dict[str, Any]] = {

    # ── TRIGGERS ─────────────────────────────────────────────────────────────
    "trigger_manual": {
        "label": "Manual Trigger",
        "category": "Triggers",
        "icon": "Play",
        "description": "Start this workflow manually with a click",
        "color": "zinc",
        "config_schema": [],
        "outputs": ["output"],
        "is_trigger": True,
    },
    "trigger_schedule": {
        "label": "Schedule Trigger",
        "category": "Triggers",
        "icon": "Clock",
        "description": "Run on a cron schedule",
        "color": "zinc",
        "config_schema": [
            {"key": "cron", "label": "Cron Expression", "type": "text", "placeholder": "0 9 * * 1-5"},
            {"key": "timezone", "label": "Timezone", "type": "text", "placeholder": "Asia/Kolkata"},
        ],
        "outputs": ["output"],
        "is_trigger": True,
    },
    "trigger_webhook": {
        "label": "Webhook Trigger",
        "category": "Triggers",
        "icon": "Webhook",
        "description": "Starts when an inbound HTTP POST arrives",
        "color": "zinc",
        "config_schema": [],
        "outputs": ["output"],
        "is_trigger": True,
    },

    # ── CORE MODULES ─────────────────────────────────────────────────────────
    "http_request": {
        "label": "HTTP Request",
        "category": "Core",
        "icon": "Globe2",
        "description": "Make a raw HTTP request to any external API",
        "color": "zinc",
        "config_schema": [
            {"key": "url", "label": "URL", "type": "text"},
            {"key": "method", "label": "Method", "type": "select",
             "options": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            {"key": "headers", "label": "Headers (JSON)", "type": "textarea", "placeholder": '{"Authorization": "Bearer token"}'},
            {"key": "body", "label": "Body (JSON)", "type": "textarea"},
        ],
        "outputs": ["response", "error"],
    },
    "set": {
        "label": "Set",
        "category": "Core",
        "icon": "Edit3",
        "description": "Set or transform variable values",
        "color": "zinc",
        "config_schema": [
            {"key": "key", "label": "Variable Name", "type": "text", "placeholder": "my_var"},
            {"key": "value", "label": "Value (use {{context.key}})", "type": "textarea"},
        ],
        "outputs": ["output"],
    },
    "code": {
        "label": "Code",
        "category": "Core",
        "icon": "Code2",
        "description": "Execute custom Python code",
        "color": "zinc",
        "config_schema": [
            {"key": "code", "label": "Python Code", "type": "textarea", "placeholder": "result = context.get('input')"}
        ],
        "outputs": ["output", "error"],
    },

    # ── LOGIC / FLOW ─────────────────────────────────────────────────────────
    "if_else": {
        "label": "If / Else",
        "category": "Logic",
        "icon": "GitBranch",
        "description": "Branch execution based on a condition",
        "color": "zinc",
        "config_schema": [
            {"key": "field", "label": "Field to Check", "type": "text", "placeholder": "node_id.status"},
            {"key": "operator", "label": "Operator", "type": "select",
             "options": ["equals", "not_equals", "greater_than", "less_than", "contains", "not_contains", "is_empty"]},
            {"key": "value", "label": "Compare Value", "type": "text"},
        ],
        "outputs": ["true", "false"],
        "is_logic": True,
    },
    "switch": {
        "label": "Switch",
        "category": "Logic",
        "icon": "Shuffle",
        "description": "Route execution down one of many paths",
        "color": "zinc",
        "config_schema": [
            {"key": "field", "label": "Field to Check", "type": "text", "placeholder": "node_id.status"},
            {"key": "cases", "label": "Cases (comma-separated)", "type": "text", "placeholder": "success, failed, pending"},
        ],
        "outputs": ["matched", "default"],
        "is_logic": True,
    },
    "loop": {
        "label": "Loop",
        "category": "Logic",
        "icon": "RefreshCw",
        "description": "Iterate over an array of items",
        "color": "zinc",
        "config_schema": [
            {"key": "array_source", "label": "Array Source", "type": "text", "placeholder": "http_request.response.items"},
        ],
        "outputs": ["item", "done"],
        "is_logic": True,
    },
    "delay": {
        "label": "Delay",
        "category": "Logic",
        "icon": "Timer",
        "description": "Wait before continuing",
        "color": "zinc",
        "config_schema": [
            {"key": "duration", "label": "Duration", "type": "number", "placeholder": "5"},
            {"key": "unit", "label": "Unit", "type": "select",
             "options": ["seconds", "minutes", "hours"]},
        ],
        "outputs": ["output"],
        "is_logic": True,
    },
    "human_review": {
        "label": "Wait for Review",
        "category": "Logic",
        "icon": "UserCheck",
        "description": "Pause execution until manual approval",
        "color": "zinc",
        "config_schema": [
            {"key": "message", "label": "Review Message", "type": "textarea", "placeholder": "Review needed for..."},
        ],
        "outputs": ["approved", "rejected"],
        "is_logic": True,
    },
    # ── LINKEDIN OUTREACH ────────────────────────────────────────────────────
    "trigger_lead_list": {
        "label": "Lead List Trigger",
        "category": "LinkedIn Outreach",
        "icon": "Users",
        "description": "Start sequence from a Vault Audience",
        "color": "blue",
        "config_schema": [
            {"key": "audience_id", "label": "Audience ID", "type": "text", "placeholder": "vault_audience_123"},
        ],
        "outputs": ["lead"],
        "is_trigger": True,
    },
    "linkedin_connect": {
        "label": "Send Connection",
        "category": "LinkedIn Outreach",
        "icon": "UserPlus",
        "description": "Send a LinkedIn connection request",
        "color": "blue",
        "config_schema": [
            {"key": "profile_url", "label": "Profile URL", "type": "text", "placeholder": "{{lead.linkedin_url}}"},
            {"key": "message", "label": "Connection Message", "type": "textarea", "placeholder": "Hi {{lead.first_name}}, let's connect!"},
        ],
        "outputs": ["sent", "failed"],
    },
    "linkedin_dm": {
        "label": "Send Message",
        "category": "LinkedIn Outreach",
        "icon": "Linkedin",
        "description": "Send a direct message to a 1st degree connection",
        "color": "blue",
        "config_schema": [
            {"key": "profile_url", "label": "Profile URL", "type": "text", "placeholder": "{{lead.linkedin_url}}"},
            {"key": "message", "label": "Message", "type": "textarea", "placeholder": "Hey {{lead.first_name}}..."},
        ],
        "outputs": ["sent", "failed"],
    },
    "linkedin_profile_visit": {
        "label": "Visit Profile",
        "category": "LinkedIn Outreach",
        "icon": "Eye",
        "description": "Visit the profile to show up in their notifications",
        "color": "blue",
        "config_schema": [
            {"key": "profile_url", "label": "Profile URL", "type": "text", "placeholder": "{{lead.linkedin_url}}"},
        ],
        "outputs": ["done"],
    },
    "linkedin_check_reply": {
        "label": "Check for Reply",
        "category": "LinkedIn Outreach",
        "icon": "MessageSquare",
        "description": "Wait and check if the lead replied",
        "color": "blue",
        "config_schema": [
            {"key": "profile_url", "label": "Profile URL", "type": "text", "placeholder": "{{lead.linkedin_url}}"},
            {"key": "wait_time", "label": "Wait Time (Days)", "type": "number", "placeholder": "3"},
        ],
        "outputs": ["replied", "no_reply"],
        "is_logic": True,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES: list[str] = ["Triggers", "LinkedIn Outreach", "Core", "Logic"]


def get_registry() -> dict[str, Any]:
    return NODE_REGISTRY


def get_node_definition(node_type: str) ->Optional[ dict[str, Any] ]:
    return NODE_REGISTRY.get(node_type)


def get_categories() -> list[str]:
    return CATEGORIES
