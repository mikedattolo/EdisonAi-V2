# Coding Workspace

## Purpose

Code Space is the first visible step toward the GitHub Copilot side of EDISON V2. It gives the workbench a real connection to the repository instead of only chat and static feature cards.

## Current Foundation

The workspace service is read-only and root-bound. It can:

- Summarize the configured workspace root.
- Scan project stack, entrypoints, package scripts, test targets, and config files.
- List files and folders while skipping heavy runtime/build directories.
- Preview text files with truncation for large files.
- Search file paths and text content.
- Discover repository instruction files (`copilot-instructions.md`, path-specific `*.instructions.md`, `AGENTS.md`, and prompt files).
- Resolve instruction context for a target file by combining repository-wide, nearest-agent, and matching path-specific instruction files.
- Build a lightweight semantic repository index for coding and review agents.
- Query that index with scored matches and snippets.
- Reject path traversal outside the configured workspace root.

The first write-capable path is intentionally review-first. Patch apply is root-bound, rejects excluded runtime/build directories, refuses binary targets, detects stale files with SHA-256 checks, and requires an explicit approval flag.

Command execution is also approval-gated. Code Space only runs commands detected by the workspace scanner, executes them without a shell, captures stdout/stderr, and records the run as a code job with events.

## API Surface

- `GET /api/v1/workspace/summary`
- `GET /api/v1/workspace/scan`
- `GET /api/v1/workspace/files?path=apps/api`
- `GET /api/v1/workspace/files/content?path=README.md`
- `POST /api/v1/workspace/search`
- `GET /api/v1/workspace/instructions`
- `GET /api/v1/workspace/instructions/context`
- `GET /api/v1/workspace/index/status`
- `POST /api/v1/workspace/index/rebuild`
- `POST /api/v1/workspace/index/search`
- `POST /api/v1/workspace/patches/preview`
- `POST /api/v1/workspace/patches/apply`
- `POST /api/v1/workspace/commands/run`

## UI Surface

The `Code Space` tab now shows:

- Workspace file and folder counts.
- Detected stack and language summary.
- Project intelligence cards for entrypoints, commands, config files, and agent queue.
- Folder browser.
- File preview.
- Inline file draft editing.
- Unified diff review with addition/deletion counts and risk flags.
- Approved command buttons for detected workspace commands.
- Command output panel with stdout, stderr, duration, exit code, and job status.
- Workspace search results that open previews.
- Instruction inventory and file-targeted instruction context resolution for coding runs.
- Rebuildable semantic index status and query results for repository intelligence.

## Next Steps

1. Persist patch proposals and approval events in job history.
2. Add command presets and validation workflow favorites.
3. Attach validation results to coding-mode chat context and agent runs.
4. Connect selected file/search context into coding-mode chat turns.
5. Add PR preparation views.
6. Persist semantic index snapshots for faster cold starts on large repositories.