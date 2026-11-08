# PatchPilot MVP Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a README-backed, clean-clone-verified PatchPilot MVP as `v0.1.0-mvp`.

**Architecture:** This is a documentation and release change, not a product behavior change. Static live-run evidence is added to the README, then the existing check script, a fresh-clone smoke test, and remote tag verification form the release gate.

**Tech Stack:** Markdown, Playwright-recorded PNG/WebM assets, PowerShell, Git, GitHub CLI/API.

**Spec:** `docs/superpowers/specs/2026-11-08-mvp-release-design.md`

## Global Constraints

- Never commit `.env`, API keys, GitHub tokens, databases, workspaces, or container secrets.
- Use repository-relative README links.
- Publish only after the full check and fresh-clone smoke test pass.
- Tag exactly the commit verified from the clean clone.

## Review Focus

- README links must resolve on GitHub and use only committed assets.
- Screenshots and result JSON must not expose credentials or local-only secrets.
- The fresh clone must not reuse the current `.venv`, `node_modules`, database, or `.env`.
- Startup validation must stop the exact test processes it creates.
- The tag and GitHub Release must resolve to the verified commit.

---

### Task 1: README live-demo evidence

**Files:**
- Modify: `README.md`
- Create: `docs/assets/patchpilot-live-diff-approval.png`
- Keep: `docs/assets/patchpilot-live-full-demo-2026-11-08-end.png`
- Keep: `docs/assets/patchpilot-live-full-demo-2026-11-08.webm`
- Keep: `docs/assets/patchpilot-live-full-demo-2026-11-08.json`

- [ ] Extract a readable Diff-approval frame from the final WebM.
- [ ] Add the two screenshots, video link, duration, run ID, branch, and commit to the README.
- [ ] Mark the live-demo roadmap item complete and verify every relative link exists.
- [ ] Scan release artifacts for credential-like strings.

### Task 2: Quality gate and main publication

**Files:** all intended release files.

- [ ] Run `scripts/check.ps1`; expect all backend tests, lint, and build to pass.
- [ ] Review the staged file list and verify `.env` is absent.
- [ ] Commit the MVP release materials and push `main`.
- [ ] Verify `origin/main` resolves to the new commit.

### Task 3: Fresh-clone startup validation

**Files:** no repository changes unless validation reveals a defect.

- [ ] Clone `origin/main` into a new temporary directory.
- [ ] Run `scripts/setup.ps1`; expect dependencies and `.env` template creation to succeed.
- [ ] Start the API and UI with `scripts/start.ps1`.
- [ ] Verify `/api/health` responds and the UI returns HTTP 200 without using the original workspace state.
- [ ] Stop the exact processes and remove the temporary clone after recording evidence.

### Task 4: Version tag and GitHub Release

**Files:**
- Update: the Day 14 Obsidian project note.

- [ ] Create annotated tag `v0.1.0-mvp` at the clean-clone-verified commit.
- [ ] Push the tag and publish GitHub Release notes with demo and evaluation highlights.
- [ ] Verify the remote tag and Release URL.
- [ ] Record final evidence in the Day 14 Obsidian note.

