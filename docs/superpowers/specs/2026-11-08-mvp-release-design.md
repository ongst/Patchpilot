# PatchPilot MVP Release Design

## Intent

Turn the existing PatchPilot MVP into a verifiable portfolio release: the README should show the human approval and successful Docker/push outcome immediately, a fresh clone must start by following the documented commands, and the verified commit must be published as `v0.1.0-mvp`.

## Goals

- Add two legible live-run screenshots and the complete WebM demo near the README introduction.
- Keep only the final live recording assets needed by readers.
- Run the full backend, lint, and frontend build gate before publishing.
- Verify `setup.ps1`, `start.ps1`, and `/api/health` from a fresh GitHub clone.
- Publish an immutable `v0.1.0-mvp` tag and GitHub Release from the verified commit.

## Non-goals

- No workflow, API, frontend, or model behavior changes.
- No deployment to a public code-execution service.
- No automatic PR creation.

## Constraints

- Never commit `.env`, API keys, GitHub tokens, database files, cloned workspaces, or test-container secrets.
- The README must use repository-relative links that work on GitHub.
- Release only after the full check and fresh-clone smoke test pass.
- The release must point at the exact commit verified from the clean clone.

## Approaches considered

1. **Two PNG screenshots plus the complete WebM (selected).** PNG keeps the approval and success evidence readable in GitHub, while WebM preserves the full 2:29 workflow.
2. **Animated GIF.** Easier to autoplay, but substantially larger and less readable for Diff and report text.
3. **Video link only.** Small README, but readers cannot understand the human-in-the-loop value without opening another artifact.

## Design

The README receives a compact “完整实时演示” section directly after the introduction. One frame shows the generated Diff at the first approval gate; the other shows `Docker PASS · Push PASS`, the branch, and the commit. The section links the final WebM and its machine-readable run result. Legacy playback assets are excluded from the release so the repository contains one authoritative demo.

Publishing is sequential: prepare assets and README, run the project gate, commit and push `main`, clone from GitHub into a temporary directory, install and start without copying local state, verify the health endpoint, then create and push `v0.1.0-mvp` and publish release notes.

