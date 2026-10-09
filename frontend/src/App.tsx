import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Code2,
  FileCode2,
  GitBranch,
  LoaderCircle,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
  X,
} from 'lucide-react'
import { API_BASE, api } from './api'
import type { Health, RunEvent, RunRecord, RunStatus } from './types'

const terminal = new Set<RunStatus>(['completed', 'completed_local', 'rejected', 'cancelled', 'failed'])

const statusLabel: Record<RunStatus, string> = {
  queued: '等待开始',
  cloning: '克隆仓库',
  profiling: '分析项目',
  baseline_testing: '基线测试',
  planning: '制定方案',
  validating_patch: '校验补丁',
  awaiting_patch_approval: '等待补丁审批',
  applying_patch: '应用补丁',
  testing: '运行测试',
  repairing: '修复重试',
  awaiting_push_approval: '等待推送审批',
  committing: '创建提交',
  pushing: '推送分支',
  completed: '已完成',
  completed_local: '本地完成',
  rejected: '已拒绝',
  cancelled: '已取消',
  failed: '失败',
}


type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'closed'

const streamStatusLabel: Record<StreamStatus, string> = {
  connecting: '连接中',
  live: '实时',
  reconnecting: '正在重连',
  closed: '已结束',
}


function StatusIcon({ status }: { status: RunStatus }) {
  if (status === 'completed' || status === 'completed_local') return <CheckCircle2 size={16} />
  if (status === 'failed' || status === 'rejected') return <AlertTriangle size={16} />
  if (status === 'cancelled') return <Square size={15} />
  if (status.startsWith('awaiting')) return <CircleDot size={16} />
  return <LoaderCircle className="spin" size={16} />
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<RunRecord | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [showCreate, setShowCreate] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('connecting')


  const refreshList = useCallback(async () => {
    try {
      const list = await api.listRuns()
      setRuns(list)
      if (!selectedId && list[0]) {
        setEvents([])
        setSelectedId(list[0].run_id)
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }, [selectedId])

  const refreshSelected = useCallback(async () => {
    if (!selectedId) return
    try {
      setSelected(await api.getRun(selectedId))
    } catch (err) {
      setError((err as Error).message)
    }
  }, [selectedId])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.listRuns().then((list) => {
      setRuns(list)
      if (list[0]) {
        setEvents([])
        setSelectedId(list[0].run_id)
      }
    }).catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    api.getRun(selectedId).then(setSelected).catch((err: Error) => setError(err.message))
    const source = new EventSource(`${API_BASE}/runs/${selectedId}/events`)
    source.onopen = () => setStreamStatus('live')
    source.onerror = () => setStreamStatus('reconnecting')

    const receive = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as RunEvent
        setEvents((current) => (current.some((item) => item.id === parsed.id) ? current : [...current, parsed]))
        void refreshSelected()
        void refreshList()
      } catch {
        // Keep-alive and terminal events do not carry RunEvent payloads.
      }
    }
    ;['created', 'status', 'profile', 'test', 'proposal', 'patch_validated', 'patch_applied', 'decision', 'completed', 'exception'].forEach(
      (name) => source.addEventListener(name, receive),
    )
    source.addEventListener('end', () => {
      setStreamStatus('closed')
      source.close()
      void refreshSelected()
      void refreshList()
    })
    return () => source.close()
  }, [selectedId, refreshList, refreshSelected])

  useEffect(() => {
    if (!selected || terminal.has(selected.status)) return
    const timer = window.setInterval(() => void refreshSelected(), 2500)
    return () => window.clearInterval(timer)
  }, [selected, refreshSelected])

  async function handleCreate(payload: { repo_url: string; issue_text: string; test_command?: string }) {
    setBusy(true)
    setError('')
    try {
      const run = await api.createRun(payload)
      setStreamStatus('connecting')
      setSelectedId(run.run_id)
      setShowCreate(false)
      await refreshList()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function decide(decision: 'approve' | 'reject', editedPatch?: string) {
    if (!selected || selected.approval_stage === 'none') return
    setBusy(true)
    setError('')
    try {
      await api.decide(selected.run_id, selected.approval_stage, decision, editedPatch)
      await refreshSelected()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Code2 size={21} /></div>
          <div><strong>PatchPilot</strong><span>Code repair agent</span></div>
        </div>
        <button className="new-run" onClick={() => setShowCreate(true)}><Play size={16} /> 新建修复任务</button>
        <div className="section-label">最近任务</div>
        <div className="run-list">
          {runs.map((run) => (
            <button
              key={run.run_id}
              className={`run-item ${selectedId === run.run_id ? 'active' : ''}`}
              onClick={() => { setEvents([]); setSelectedId(run.run_id); setShowCreate(false); setStreamStatus('connecting') }}
            >
              <StatusIcon status={run.status} />
              <span><strong>{repoName(run.repo_url)}</strong><small>{statusLabel[run.status]}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!runs.length && <p className="empty-small">还没有运行记录</p>}
        </div>
        <div className="health-card">
          <div><Activity size={15} /> 系统状态 <span className={`dot ${health?.status ?? 'offline'}`} /></div>
          <small>DB {health?.database ? '✓' : '×'} · Git {health?.git ? '✓' : '×'} · Docker {health?.docker ? '✓' : '×'} · LLM {health?.llm_configured ? '✓' : '×'}</small>
          <small>修复：{health?.ready_for_repair ? '可用' : '未就绪'} · 推送：{health?.ready_for_push ? '可用' : '未就绪'}</small>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div><span className="eyebrow">HUMAN-IN-THE-LOOP</span><h1>{showCreate ? '开始一次安全修复' : selected ? repoName(selected.repo_url) : 'PatchPilot'}</h1></div>
          <button className="icon-button" onClick={() => { void refreshList(); void refreshSelected() }} title="刷新"><RefreshCw size={17} /></button>
        </header>
        {error && <div className="error-banner"><AlertTriangle size={17} />{error}<button onClick={() => setError('')}><X size={15} /></button></div>}
        {showCreate ? <CreateRun busy={busy} onSubmit={handleCreate} /> : selected ? (
          <RunDetail key={`${selected.run_id}-${selected.attempt_count}-${selected.approval_stage}`} run={selected} events={events} busy={busy} onDecision={decide} onCancel={async () => { await api.cancel(selected.run_id); await refreshSelected() }} streamStatus={streamStatus} />
        ) : <div className="empty-state"><Code2 size={44} /><h2>选择或创建一个修复任务</h2></div>}
      </main>
    </div>
  )
}

function CreateRun({ busy, onSubmit }: { busy: boolean; onSubmit: (payload: { repo_url: string; issue_text: string; test_command?: string }) => Promise<void> }) {
  const [repo, setRepo] = useState('')
  const [issue, setIssue] = useState('')
  const [command, setCommand] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    void onSubmit({ repo_url: repo, issue_text: issue, test_command: command || undefined })
  }
  return (
    <section className="create-layout">
      <form className="create-card" onSubmit={submit}>
        <div className="card-heading"><GitBranch size={20} /><div><h2>连接公开 GitHub 仓库</h2><p>PatchPilot 只会在隔离的 <code>patchpilot/*</code> 分支中工作。</p></div></div>
        <label>仓库地址<input type="url" required placeholder="https://github.com/owner/repository" value={repo} onChange={(e) => setRepo(e.target.value)} /></label>
        <label>Issue 描述<textarea required minLength={10} rows={8} placeholder="描述复现方式、期望行为和当前错误……" value={issue} onChange={(e) => setIssue(e.target.value)} /></label>
        <label>测试命令 <span>可选</span><input placeholder="python -m pytest -q 或 npm test" value={command} onChange={(e) => setCommand(e.target.value)} /></label>
        <button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />} 启动修复</button>
      </form>
      <div className="principles">
        <h3>默认安全边界</h3>
        {[['受限工具', '模型只能搜索、读取并提出统一 Diff。'], ['双重审批', '应用补丁和推送分支前分别暂停。'], ['隔离测试', '限制资源、移除密钥并关闭测试网络。'], ['永不合并', '只推送新分支，不触碰默认分支。']].map(([title, text]) => <div className="principle" key={title}><ShieldCheck size={18} /><div><strong>{title}</strong><p>{text}</p></div></div>)}
      </div>
    </section>
  )
}

function RunDetail({ run, events, busy, onDecision, onCancel, streamStatus }: { run: RunRecord; events: RunEvent[]; busy: boolean; onDecision: (decision: 'approve' | 'reject', patch?: string) => Promise<void>; onCancel: () => Promise<void>; streamStatus: StreamStatus }) {
  const [editedPatch, setEditedPatch] = useState(run.patch)
  const progress = useMemo(() => statusProgress(run.status), [run.status])
  return (
    <div className="run-detail">
      <section className="summary-strip">
        <div><span>状态</span><strong className={`status-pill ${run.status}`}><StatusIcon status={run.status} /> {statusLabel[run.status]}</strong></div>
        <div><span>语言</span><strong>{run.language}</strong></div>
        <div><span>尝试</span><strong>{run.attempt_count || '—'} / 3</strong></div>
        <div><span>Token</span><strong>{run.token_usage.toLocaleString()}</strong></div>
        <div><span>分支</span><strong className="mono">{run.branch_name || 'pending'}</strong></div>
      </section>
      <div className="progress"><span style={{ width: `${progress}%` }} /></div>
      <div className="detail-grid">
        <div className="content-column">
          <Panel title="Issue" icon={<FileCode2 size={18} />}><p className="issue-text">{run.issue_text}</p></Panel>
          {run.repair_plan && <Panel title="修复方案" icon={<Code2 size={18} />}>
            <h3>{run.repair_plan.summary}</h3><p>{run.repair_plan.root_cause}</p>
            <ol>{run.repair_plan.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            {!!run.repair_plan.risks.length && <div className="risk"><AlertTriangle size={16} /><span>{run.repair_plan.risks.join('；')}</span></div>}
          </Panel>}
          {run.patch && <Panel title="Unified Diff" icon={<GitBranch size={18} />}>
            {run.approval_stage === 'apply_patch' ? <textarea className="diff-editor" value={editedPatch} onChange={(e) => setEditedPatch(e.target.value)} spellCheck={false} /> : <pre className="diff-view">{run.patch}</pre>}
          </Panel>}
          {(run.baseline_result || run.test_result) && <Panel title="测试" icon={<CheckCircle2 size={18} />}>
            {[run.baseline_result, run.test_result].filter(Boolean).map((result) => result && <div className={`test-result ${result.passed ? 'pass' : 'fail'}`} key={result.phase}>
              <div><strong>{result.phase === 'baseline' ? '基线' : '修复后'}</strong><code>{result.command}</code><span>{result.skipped_reason ?? (result.passed ? 'PASS' : `EXIT ${result.exit_code}`)}</span></div>
              {result.output && <pre>{result.output}</pre>}
            </div>)}
          </Panel>}
          {run.error && <div className="error-card"><AlertTriangle size={20} /><div><strong>运行未完成</strong><p>{run.error}</p></div></div>}
        </div>
        <aside className="timeline-column">
          <Panel title="执行轨迹" icon={<Activity size={18} />} badge={<span className={`stream-status ${streamStatus}`}>{streamStatusLabel[streamStatus]}</span>}>
            <div className="timeline">
              {events.map((event) => <div className={`timeline-event ${event.level}`} key={event.id}><span /><div><strong>{event.message}</strong><small>{new Date(event.created_at).toLocaleTimeString()}</small></div></div>)}
              {!events.length && <p className="empty-small">等待事件……</p>}
            </div>
          </Panel>
          {run.inspected_files.length > 0 && <Panel title="已检查文件" icon={<FileCode2 size={18} />}><ul className="file-list">{run.inspected_files.map((file) => <li key={file}>{file}</li>)}</ul></Panel>}
        </aside>
      </div>
      {run.approval_stage !== 'none' && <div className="approval-bar"><div><ShieldCheck size={22} /><span><strong>{run.approval_stage === 'apply_patch' ? '是否应用这份补丁？' : '是否提交并推送这个新分支？'}</strong><small>这是一个需要人工确认的高影响操作。</small></span></div><div><button className="reject" disabled={busy} onClick={() => void onDecision('reject')}>拒绝</button><button className="approve" disabled={busy} onClick={() => void onDecision('approve', run.approval_stage === 'apply_patch' ? editedPatch : undefined)}><Check size={17} />批准</button></div></div>}
      {!terminal.has(run.status) && run.approval_stage === 'none' && <button className="cancel-run" onClick={() => void onCancel()}>取消运行</button>}
    </div>
  )
}

function Panel({ title, icon, badge, children }: { title: string; icon: React.ReactNode; badge?: React.ReactNode; children: React.ReactNode }) {
  return <section className="panel"><div className="panel-title">{icon}<h2>{title}</h2>{badge}</div><div className="panel-body">{children}</div></section>
}

function repoName(url: string) { return url.replace(/\/$/, '').split('/').slice(-2).join('/') }

function statusProgress(status: RunStatus) {
  const steps: RunStatus[] = ['queued', 'cloning', 'profiling', 'baseline_testing', 'planning', 'validating_patch', 'awaiting_patch_approval', 'applying_patch', 'testing', 'awaiting_push_approval', 'committing', 'pushing', 'completed']
  if (terminal.has(status)) return status === 'completed' || status === 'completed_local' ? 100 : 92
  const index = steps.indexOf(status === 'repairing' ? 'planning' : status)
  return Math.max(4, ((index + 1) / steps.length) * 100)
}

export default App
