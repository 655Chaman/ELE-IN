import { fetchWithAuth } from './apiClient'
const API_BASE = "/api"

// ─── Workflow CRUD ───────────────────────────────────────────────────────────

export async function fetchWorkflows() {
  const res = await fetchWithAuth(`${API_BASE}/workflows`)
  if (!res.ok) throw new Error("Failed to fetch workflows")
  return res.json()
}

export async function fetchWorkflow(id: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${id}`)
  if (!res.ok) throw new Error("Workflow not found")
  return res.json()
}

export async function createWorkflow(payload: {
  name: string
  description?: string
  definition?: any
}) {
  const res = await fetchWithAuth(`${API_BASE}/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error("Failed to create workflow")
  return res.json()
}

export async function saveWorkflow(id: string, payload: {
  name?: string
  description?: string
  definition?: any
}) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error("Failed to save workflow")
  return res.json()
}

export async function deleteWorkflow(id: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${id}`, { method: "DELETE" })
  if (!res.ok) throw new Error("Failed to delete workflow")
  return res.json()
}

export async function duplicateWorkflow(id: string, name: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${id}/duplicate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error("Failed to duplicate workflow")
  return res.json()
}

// ─── Execution ───────────────────────────────────────────────────────────────

export async function runWorkflow(id: string, context: Record<string, any> = {}) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${id}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context }),
  })
  if (!res.ok) throw new Error("Failed to start workflow")
  return res.json()
}

export async function fetchRunStatus(workflowId: string, runId: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${workflowId}/runs/${runId}`)
  if (!res.ok) throw new Error("Run not found")
  return res.json()
}

export async function stopWorkflowRun(workflowId: string, runId: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${workflowId}/runs/${runId}/stop`, {
    method: "POST",
  })
  if (!res.ok) throw new Error("Failed to stop run")
  return res.json()
}

export async function fetchRunHistory(workflowId: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${workflowId}/runs`)
  if (!res.ok) throw new Error("Failed to fetch runs")
  return res.json()
}

// ─── Node Registry ───────────────────────────────────────────────────────────

export async function fetchNodeRegistry() {
  const res = await fetchWithAuth(`${API_BASE}/workflows/registry`)
  if (!res.ok) throw new Error("Failed to fetch node registry")
  return res.json()
}

// ─── Version History ─────────────────────────────────────────────────────────

export async function fetchVersions(workflowId: string) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${workflowId}/versions`)
  if (!res.ok) throw new Error("Failed to fetch versions")
  return res.json()
}

export async function restoreVersion(workflowId: string, version: number) {
  const res = await fetchWithAuth(`${API_BASE}/workflows/${workflowId}/restore/${version}`, {
    method: "POST",
  })
  if (!res.ok) throw new Error("Failed to restore version")
  return res.json()
}
