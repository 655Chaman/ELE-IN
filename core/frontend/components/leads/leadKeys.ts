/**
 * Canonical SWR cache key factory for the LEADS subsystem.
 * Eliminates cache drift and key fragmentation across all views, drawers, and studios.
 * 
 * Paranoia Layer 1 & 2: Guarantees unified workspace-scoped key identity across
 * EleInLeads, DynamicSegmentationStudioModal, SocialSignalRadarView, and ListLeadsDrawer.
 */
export const leadKeys = {
  lists: (workspaceId?: string | null) => 
    workspaceId ? `/api/elein/leads/lists?workspace_id=${workspaceId}` : '/api/elein/leads/lists',
  
  radarFeed: (workspaceId?: string | null, tierFilter?: string) => {
    const wsParam = workspaceId ? `workspace_id=${workspaceId}` : ''
    const tierParam = tierFilter && tierFilter !== 'ALL' ? `tier=${tierFilter}` : ''
    const params = [tierParam, wsParam].filter(Boolean).join('&')
    return `/api/leads/social-radar/feed${params ? `?${params}` : ''}`
  },

  listLeads: (listId: string, page: number = 1, pageSize: number = 50, search?: string) => {
    const qParam = search && search.trim() ? `&q=${encodeURIComponent(search.trim())}` : ''
    return `/api/leads/lists/${listId}/leads?page=${page}&page_size=${pageSize}${qParam}`
  },

  campaigns: (workspaceId?: string | null) =>
    workspaceId ? `/api/elein/campaigns?workspace_id=${workspaceId}` : '/api/elein/campaigns',

  accounts: (workspaceId?: string | null) =>
    workspaceId ? `/api/elein/accounts?workspace_id=${workspaceId}` : '/api/elein/accounts',

  billing: (workspaceId?: string | null) =>
    workspaceId ? `/api/elein/workspaces/billing?workspace_id=${workspaceId}` : '/api/elein/workspaces/billing',
}
