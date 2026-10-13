import type { ApprovalStage, Health, DiffResponse, RunRecord } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? 'Request failed')
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/health'),
  listRuns: () => request<RunRecord[]>('/runs'),
  getRun: (runId: string) => request<RunRecord>(`/runs/${runId}`),
  createRun: (payload: { repo_url: string; issue_text: string; test_command?: string }) =>
    request<RunRecord>('/runs', { method: 'POST', body: JSON.stringify(payload) }),
  decide: (
    runId: string,
    stage: ApprovalStage,
    decision: 'approve' | 'reject',
    editedPatch?: string,
  ) =>
    request<RunRecord>(`/runs/${runId}/decisions`, {
      method: 'POST',
      body: JSON.stringify({ stage, decision, edited_patch: editedPatch || null }),
    }),
  cancel: (runId: string) => request<RunRecord>(`/runs/${runId}/cancel`, { method: 'POST' }),
  getDiff: (runId: string) => request<DiffResponse>(`/runs/${runId}/diff`),
}

