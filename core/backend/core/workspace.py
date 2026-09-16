"""
Workspace resolution helper.
Resolves workspace_id for the current authenticated user.

Schema v2 note: workspaces.user_id no longer exists.
Workspace membership is tracked via the workspace_members join table.
"""
from typing import Optional
from supabase import Client


def get_workspace_id(supabase: Client, user_id: Optional[str] = None) -> str:
    """
    Fetch the primary workspace_id for the given user_id.
    Schema v2: queries workspace_members (owner row, ordered by created_at ASC).

    Args:
        supabase: Supabase client (service role)
        user_id: The auth.users UUID. If None, raises ValueError.

    Returns:
        workspace_id as a string UUID

    Raises:
        ValueError if no workspace found
    """
    if not user_id:
        raise ValueError("user_id is required to resolve workspace_id")

    # Schema v2: workspaces.user_id removed — join via workspace_members
    res = (
        supabase.table("workspace_members")
        .select("workspace_id")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise ValueError(
            f"No workspace found for user_id={user_id}. "
            "User may not have completed onboarding."
        )
    return res.data[0]["workspace_id"]


def get_workspace_id_safe(supabase: Client, user_id: Optional[str] = None) -> Optional[str]:
    """Same as get_workspace_id but returns None instead of raising."""
    try:
        return get_workspace_id(supabase, user_id)
    except Exception:
        return None
