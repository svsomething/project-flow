---
name: project-workflow
description: Handle a mini-agentic kanban project task. Use when asked to plan, implement, or iterate on a GitHub issue that is part of the mini-agentic project board. Triggered by project-monitor or manually ("plan issue #N", "implement issue #N", "pick up issue #N").
tools: Bash, Read, Write, Edit, Glob, Grep
---

# Project Workflow

Handle one action for a GitHub issue on the mini-agentic kanban board.

## Phase 1: Read configuration

All deployment-specific values live in `config.yaml` at the root of the `project-flow` repo. Read it first:

```bash
cat ~/repos/project-flow/config.yaml
```

Extract the values you need:
- `github.org` → GitHub username/org (used in GraphQL queries)
- `github.bot_login` → bot account login
- `github.bot_token_file` → path to bot token file
- `project.number` → project board number
- `project.id` → project node ID for GraphQL mutations
- `project.status_field_id` → Status field ID for GraphQL mutations
- `project.columns.in_review` → option ID for the In Review column
- `project.columns.done` → option ID for the Done column

All `gh` commands must use the bot token:
```bash
export GH_TOKEN=$(cat <bot_token_file from config>)
```

## Phase 2: Determine action

Read the invoking context to identify:
- **Issue number** and **repo** (e.g. `svsomething/infra`)
- **Action**: one of `plan`, `iterate`, `implement`, or `done`
  - `plan` — no bot comment exists yet on this issue
  - `iterate` — bot has posted a plan; there are new user comments since the last bot reply
  - `implement` — issue is in the Implement column
  - `done` — all PRs linked to the issue are approved; merge them and wrap up

If not provided directly, run:
```bash
gh issue view <N> -R <repo> --json number,title,body,comments
```

## Phase 3: Execute

### Action: plan

Read the issue title and body. Create a thorough implementation plan and post it as a comment:

```bash
gh issue comment <N> -R <repo> --body "## Plan

<detailed plan covering:
- What will be implemented and why
- Step-by-step approach
- Files to be created or modified
- Open questions or decisions needing input>

---
*Waiting for your feedback. Move the card to **Implement** when you're ready to proceed.*"
```

### Action: iterate

Read the full comment thread:
```bash
gh issue view <N> -R <repo> --json comments
```

Understand the user's latest feedback. Post a refined response — update the plan, answer questions, or confirm the approach:

```bash
gh issue comment <N> -R <repo> --body "<response to feedback>"
```

If the plan is solid and no changes are needed, end with:
```
---
*Plan looks good. Move the card to **Implement** when you're ready.*
```

### Action: implement

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "## Starting implementation

Beginning work now. I will open PRs when complete."
```

2. **Read the plan** from the issue comment thread (latest bot comment starting with `## Plan`).

3. **Implement** in the local repo clone (find the path using `repos.root` from config):
   - Create feature branch: `git checkout -b feat/issue-<N>-<short-description>`
   - Make all changes per the plan
   - Update `CONTEXT.md` (and `README.md` if applicable) in each affected repo to reflect what changed — so the context diff is visible in the PR alongside the code
   - Commit everything together with descriptive messages

4. **Open PR(s)** — include `Closes #<N>` in the body. Always include a `## Post-merge` section — even when there is nothing to do. When there are no post-merge steps, write a short sentence explaining why (e.g. "No post-merge actions required — changes are self-contained and take effect after merge."). Never omit the section:
```bash
gh pr create -R <repo> \
  --title "<title>" \
  --body "Closes #<N>

## Summary
<what was implemented>

## Post-merge
- pull: \`~/repos/project-flow\` \`~/repos/infra\`
- run: \`<shell command, e.g. docker restart homeassistant>\`"
```

   When there are no post-merge steps, use free-form prose to explain why, for example:
   `No post-merge actions required — changes are self-contained within the repo and take effect after merge without any restart, pull, or deploy steps.`

   **After opening each PR, register it in the pr-monitor state file** so monitoring begins immediately (without waiting for the next auto-registration cycle):
```bash
PR_NUM=$(gh pr view --json number --jq .number -R <repo>)
LOCAL_REPO=$(realpath ~/repos/<repo-name>)
STATE=~/.claude/pr-monitor-state.json
python3 - <<PYEOF
import json, pathlib
f = pathlib.Path('$STATE')
state = json.loads(f.read_text()) if f.exists() else []
entry = {"repo": "$LOCAL_REPO", "pr": $PR_NUM}
if entry not in state:
    state.append(entry)
    f.write_text(json.dumps(state, indent=2))
PYEOF
```

   **Permission notes (no sudo needed):**
   - `~/docker-data/` is owned by `scottv` — use plain `cp`, not `sudo cp`
   - `scottv` is in the `docker` group — use `docker` commands directly, not `sudo docker`

5. **Move card to In Review** via GraphQL mutation (use values from config.yaml):
```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "<project.id from config>"
    itemId: "<project-item-id>"
    fieldId: "<project.status_field_id from config>"
    value: { singleSelectOptionId: "<project.columns.in_review from config>" }
  }) { projectV2Item { id } }
}'
```

   Get the project item ID from the invoking context, or query:
```bash
gh api graphql -f query='
{
  user(login: "<github.org from config>") {
    projectV2(number: <project.number from config>) {
      items(first: 50) {
        nodes {
          id
          content { ... on Issue { number } }
        }
      }
    }
  }
}'
```

6. **Post summary comment** with PR links:
```bash
gh issue comment <N> -R <repo> --body "## Implementation complete

PRs opened:
- <PR URL>

The card has been moved to In Review."
```

### Action: done

All PRs linked to the issue are approved. Squash-merge them, update all repos, run post-merge steps, and close out the card.

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "## Merging PRs

All PRs are approved. Squash-merging and wrapping up now."
```

2. **Find all open PRs linked to the issue** — prefer the list passed in the invoking prompt (e.g. "PRs to merge: #10 in svsomething/project-flow, #24 in svsomething/infra"). If no list was provided, fall back to the timeline API (which covers cross-repo PRs):
```bash
export GH_TOKEN=$(cat <bot_token_file from config>)
gh api repos/<repo>/issues/<N>/timeline --paginate \
  --jq '[.[] | select(.event=="cross-referenced") | select(.source.issue.pull_request != null) | .source.issue | {number: .number, state: .state, repo: .repository.full_name}] | map(select(.state=="open"))'
```

3. **Verify all are still APPROVED** (guard against a race condition) — use each PR's own repo:
```bash
gh pr view <PR-number> -R <pr-repo> --json reviewDecision,reviews
```
A PR is approved if `reviewDecision == "APPROVED"` **or** any entry in `reviews` has `state == "APPROVED"` (GitHub only sets `reviewDecision` when branch protection requires reviews).
If any PR is not approved, abort and post a comment explaining why.

4. **Squash-merge each PR and delete the branch** — use each PR's own repo:
```bash
gh pr merge <PR-number> -R <pr-repo> --squash --delete-branch
```

5. **Pull all repos to latest main** (check `repos.root` in config for the root path):
```bash
git -C ~/repos/project-flow checkout main && git -C ~/repos/project-flow pull origin main
git -C ~/repos/infra  checkout main && git -C ~/repos/infra  pull origin main
```

6. **Run post-merge commands** — for each PR body, parse the `## Post-merge` section:
   - Extract any `- run: \`...\`` lines and execute them as shell commands
   - Skip if no `## Post-merge` section or no `run:` lines are present

7. **Move card to Done** (use values from config.yaml):
```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "<project.id from config>"
    itemId: "<project-item-id>"
    fieldId: "<project.status_field_id from config>"
    value: { singleSelectOptionId: "<project.columns.done from config>" }
  }) { projectV2Item { id } }
}'
```

8. **Post completion summary:**
```bash
gh issue comment <N> -R <repo> --body "## Done

All PRs squash-merged, branches deleted, repos pulled to latest main.

The card has been moved to Done."
```

## Phase 4: Confirm

Report what was done in one concise sentence. No approval needed.

## Automated driver

This skill is designed to be invoked by `project-monitor` (at `project-flow/scripts/project-monitor`), which polls the GitHub Project board, detects when cards move between columns, and dispatches Claude with the appropriate action (`plan`, `iterate`, `implement`, or `done`). You can also invoke it manually ("plan issue #N", "implement issue #N").
