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
   - Commit with descriptive messages

4. **Open PR(s)** — include `Closes #<N>` and a post-merge block in the body:
```bash
gh pr create -R <repo> \
  --title "<title>" \
  --body "Closes #<N>

## Summary
<what was implemented>

<!-- post-merge
pull: ~/repos/skills ~/repos/infra
run: <optional shell commands, e.g. docker restart homeassistant — omit line if none needed>
-->"
```

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

2. **Find all open PRs linked to the issue** (use the implementation comment or search):
```bash
export GH_TOKEN=$(cat ~/.config/bot-gh-token)
gh pr list -R <repo> --search "Closes #<N> is:open" --json number,title,headRefName,body
```

3. **Verify all are still APPROVED** (guard against a race condition):
```bash
gh pr view <PR-number> -R <repo> --json reviewDecision
```
If any PR is not `APPROVED`, abort and post a comment explaining why.

4. **Squash-merge each PR and delete the branch:**
```bash
gh pr merge <PR-number> -R <repo> --squash --delete-branch
```

5. **Pull all repos to latest main:**
```bash
git -C ~/repos/skills pull origin main
git -C ~/repos/infra pull origin main
```

6. **Run post-merge commands** — for each PR body, parse the `<!-- post-merge ... -->` block:
   - Extract any `run:` lines and execute them as shell commands
   - Skip if no block or no `run:` line present

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
