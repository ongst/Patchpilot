export type RunStatus =
  | 'queued'
  | 'cloning'
  | 'profiling'
  | 'baseline_testing'
  | 'planning'
  | 'validating_patch'
  | 'awaiting_patch_approval'
  | 'applying_patch'
  | 'testing'
  | 'repairing'
  | 'awaiting_push_approval'
  | 'committing'
  | 'pushing'
  | 'completed'
  | 'completed_local'
  | 'rejected'
  | 'cancelled'
  | 'failed'

export type ApprovalStage = 'none' | 'apply_patch' | 'push_branch'

export interface RepairPlan {
  summary: string
  root_cause: string
  steps: string[]
  tests: string[]
  risks: string[]
}

export interface TestResult {
  command: string
  exit_code: number | null
  passed: boolean
  output: string
  duration_seconds: number
  phase: 'baseline' | 'post_patch'
  skipped_reason: string | null
}

export interface RunRecord {
  run_id: string
  status: RunStatus
  repo_url: string
  issue_text: string
  test_command: string | null
  language: 'python' | 'javascript' | 'unknown'
  branch_name: string
  workspace: string
  repair_plan: RepairPlan | null
  inspected_files: string[]
  patch: string
  attempt_count: number
  baseline_result: TestResult | null
  test_result: TestResult | null
  approval_stage: ApprovalStage
  commit_sha: string
  remote_branch: string
  token_usage: number
  error: string
  created_at: string
  updated_at: string
}

export interface RunEvent {
  id: number
  run_id: string
  level: 'info' | 'warning' | 'error'
  event_type: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

export interface Health {
  status: 'ok' | 'degraded'
  database: boolean
  git: boolean
  docker: boolean
  llm_configured: boolean
  version: string
  ready_for_repair: boolean
  ready_for_push: boolean
}

export interface DiffFileSummary {
  path: string
  additions: number
  deletions: number
}

export interface DiffResponse {
  run_id: string
  patch: string
  files: DiffFileSummary[]
  additions: number
  deletions: number
  changed_lines: number
}

