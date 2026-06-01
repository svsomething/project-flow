---
name: project-workflow
description: Handle a mini-agentic kanban project task. Use when asked to plan, implement, or iterate on a GitHub issue that is part of the mini-agentic project board. Triggered by project-monitor or manually ("plan issue #N", "implement issue #N", "pick up issue #N").
tools: Bash, Read, Write, Edit, Glob, Grep
---

# Project Workflow

Handle one action for a GitHub issue on the mini-agentic kanban board.

## Constants (do not change)

```
PROJECT_ID    = PVT_kwHOERrops4BZOd2
STATUS_FIELD  = PVTSSF_lAHOERrops4BZOd2zhUOqxg
OPTION_IN_REVIEW = df73e18b
OPTION_DONE      = 98236657
BOT_TOKEN_FILE   = ~/.config/bot-gh-token
BOT_LOGIN        = svsomething-bot
```

All `gh` commands must use the bot token:
```bash
export GH_TOKEN=$(cat ~/.config/bot-gh-token)
```

## Phase 1: Determine action

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

## Phase 2: Execute

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

3. **Implement** in the local repo (e.g. `~/repos/infra` or `~/repos/skills`):
   - Create feature branch: `git checkout -b feat/issue-<N>-<short-description>`
   - Make all changes per the plan
   - Update `CONTEXT.md` (and `README.md` if applicable) in each affected repo to reflect what changed — so the context diff is visible in the PR alongside the code
   - Commit everything together with descriptive messages

4. **Open PR(s)** — include `Closes #<N>` in the body. If there are post-merge steps, append a `## Post-merge` section; omit it entirely if there are none:
```bash
gh pr create -R <repo> \
  --title "<title>" \
  --body "Closes #<N>

## Summary
<what was implemented>

## Post-merge
- pull: \`~/repos/skills\` \`~/repos/infra\`
- run: \`<shell command, e.g. docker restart homeassistant>\`"
```

   Omit the `## Post-merge` section entirely when there are no post-merge steps.

   **Permission notes (no sudo needed):**
   - `~/docker-data/` is owned by `scottv` — use plain `cp`, not `sudo cp`
   - `scottv` is in the `docker` group — use `docker` commands directly, not `sudo docker`

5. **Move card to In Review** via GraphQL mutation:
```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "PVT_kwHOERrops4BZOd2"
    itemId: "<project-item-id>"
    fieldId: "PVTSSF_lAHOERrops4BZOd2zhUOqxg"
    value: { singleSelectOptionId: "df73e18b" }
  }) { projectV2Item { id } }
}'
```

   Get the project item ID from the invoking context, or query:
```bash
gh api graphql -f query='
{
  user(login: "svsomething") {
    projectV2(number: 1) {
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

2. **Find all open PRs linked to the issue** — prefer the list passed in the invoking prompt (e.g. "PRs to merge: #10 in svsomething/skills, #24 in svsomething/infra"). If no list was provided, fall back to the timeline API (which covers cross-repo PRs):
```bash
export GH_TOKEN=$(cat ~/.config/bot-gh-token)
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

5. **Pull all repos to latest main:**
```bash
git -C ~/repos/skills checkout main && git -C ~/repos/skills pull origin main
git -C ~/repos/infra  checkout main && git -C ~/repos/infra  pull origin main
```

6. **Run post-merge commands** — for each PR body, parse the `## Post-merge` section:
   - Extract any `- run: \`...\`` lines and execute them as shell commands
   - Skip if no `## Post-merge` section or no `run:` lines are present

7. **Move card to Done:**
```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "PVT_kwHOERrops4BZOd2"
    itemId: "<project-item-id>"
    fieldId: "PVTSSF_lAHOERrops4BZOd2zhUOqxg"
    value: { singleSelectOptionId: "98236657" }
  }) { projectV2Item { id } }
}'
```

   Get the project item ID from the invoking context, or query:
```bash
gh api graphql -f query='
{
  user(login: "svsomething") {
    projectV2(number: 1) {
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

8. **Post completion summary:**
```bash
gh issue comment <N> -R <repo> --body "## Done

All PRs squash-merged, branches deleted, repos pulled to latest main.

The card has been moved to Done."
```

## Phase 3: Confirm

Report what was done in one concise sentence. No approval needed.

## Automated driver

This skill is designed to be invoked by `project-monitor` (at `infra/scripts/project-monitor`), which polls GitHub Project #1, detects when cards move between columns, and dispatches Claude with the appropriate action (`plan`, `iterate`, `implement`, or `done`). You can also invoke it manually ("plan issue #N", "implement issue #N").
