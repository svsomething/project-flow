---
name: pr-workflow
description: Create a feature branch, commit all pending changes, push, and open a GitHub PR with rich context (original request, plan, implementation notes). Use when the user says "submit as PR", "open a PR", "push for review", "create a pull request", or similar.
tools: Bash, Read, Write
---

# PR Workflow

Turn the current implementation into a GitHub PR ready for human review.

## Phase 1: Gather context

1. Confirm we're in a git repo with a GitHub remote:
   ```bash
   git remote get-url origin
   ```
   If no remote, stop and tell the user.

2. Capture current state:
   ```bash
   git status --short
   git branch --show-current
   git log --oneline -5
   ```

3. Extract from conversation context:
   - **Original request**: what the user asked for (verbatim if possible)
   - **Plan**: what was agreed before implementation
   - **Summary**: what was actually implemented (2–5 bullets)
   - **Deviations**: anything that differed from the plan (if none, omit)

## Phase 2: Prepare the branch

1. If already on a feature branch (not `main`/`master`/`develop`), use it.
   Otherwise, derive a branch name from the task:
   - Format: `feat/<short-kebab-summary>` or `fix/<short-kebab-summary>`
   - Max 40 chars, lowercase, hyphens only
   - Example: `feat/add-nginx-docker-stack`

2. Create and checkout the branch (if needed):
   ```bash
   git checkout -b <branch-name>
   ```

3. Stage and commit any uncommitted changes:
   ```bash
   git add -A
   git status --short   # confirm what's being committed
   git commit -m "<conventional-commit-message>"
   ```
   If there's nothing to commit, note that and continue.

4. Push to origin:
   ```bash
   git push -u origin <branch-name>
   ```

## Phase 3: Create the PR

Create the PR using this body template. Fill every section from conversation context — do not leave placeholders.

```bash
gh pr create \
  --title "<concise title, under 70 chars>" \
  --body "$(cat <<'PRBODY'
## Summary
<!-- 2–5 bullets describing what was implemented -->

## Original Request
<!-- Verbatim or close paraphrase of what the user asked for -->

## Plan
<!-- What was agreed / planned before implementation -->

## Implementation Notes
<!-- What was actually done; note any deviations from the plan -->

## Test Plan
- [ ] <!-- How to verify the primary change works -->
- [ ] <!-- Edge cases or regressions to check -->

---
🤖 Implemented with [Claude Code](https://claude.ai/code)
PRBODY
)"
```

## Phase 4: Register with the PR monitor

Append the PR to the monitor state file so the background monitor can track it:

```bash
python3 - <<'EOF'
import json, os, datetime

state_file = os.path.expanduser("~/.claude/pr-monitor-state.json")
try:
    with open(state_file) as f:
        state = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    state = []

import subprocess
repo = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
pr_num = int(subprocess.check_output(
    ["gh", "pr", "view", "--json", "number", "--jq", ".number"], text=True).strip())

# Remove any existing entry for this repo/branch
state = [e for e in state if not (e["repo"] == repo and e["branch"] == branch)]
state.append({
    "repo": repo,
    "pr": pr_num,
    "branch": branch,
    "added_at": datetime.datetime.utcnow().isoformat() + "Z"
})

with open(state_file, "w") as f:
    json.dump(state, f, indent=2)
print(f"Registered PR #{pr_num} in {state_file}")
EOF
```

## Phase 5: Report to user

Output:
- PR URL (from `gh pr view --json url --jq .url`)
- Branch name
- One-line reminder: "The PR monitor will check for review comments every 5 minutes and address them automatically. Approve the PR on GitHub to trigger auto-merge."
