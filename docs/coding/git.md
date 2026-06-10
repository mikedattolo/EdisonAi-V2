# Git Reference & Workflow

Edison's repo is git, remote on GitHub (`mikedattolo/EdisonAi-V2`). The Code Agent may only run READ-ONLY git (`status`, `diff`, `log`, `branch`, `show`); commits/pushes are done deliberately.

## Inspect (safe, allowed)
- `git status` / `git status -s` — what changed.
- `git diff` — unstaged changes; `git diff --staged` — staged; `git diff <file>`; `git diff --stat`.
- `git log --oneline -10`; `git log -p <file>`; `git show <rev>` — a commit's changes.
- `git branch` list; `git branch --show-current`.

## Stage & commit
- Stage: `git add <file>` (specific is safest) or `git add -A` (everything). Unstage: `git restore --staged <file>`.
- Commit: `git commit -m "subject" -m "body paragraph"` (repeat `-m` for paragraphs). Amend last (if unpushed): `git commit --amend`.
- Discard local edits to a file: `git checkout -- <file>` (irreversible for uncommitted work — be sure).

## Branches & history
- New branch: `git switch -c feature-x` (or `git checkout -b feature-x`). Switch: `git switch main`.
- Merge: `git merge feature-x`. Rebase (linear history): `git rebase main` (avoid on shared branches).
- Undo a commit keeping changes: `git reset --soft HEAD~1`; discard a commit and changes: `git reset --hard HEAD~1` (destructive).

## Remote (GitHub)
- `git remote -v`; fetch `git fetch origin`; pull `git pull --ff-only`; push `git push origin main`.
- HTTPS auth needs a Personal Access Token (not a password). On a box without stored creds, push from a machine that has them, or use a credential helper / SSH key.

## .gitignore
- Patterns ignore untracked files: `node_modules/`, `.venv/`, `dist/`, `__pycache__/`, `*.log`, `.env`.

## Good practices
- Small, focused commits with clear messages (imperative subject: "Add X", "Fix Y").
- Commit only intended files (stage explicitly). Never commit secrets, tokens, or large build artifacts.
- Check `git status` and `git diff` before committing; check `git log` before pushing.
- Treat `reset --hard`, `clean -fd`, force-push as dangerous — confirm the target first.
