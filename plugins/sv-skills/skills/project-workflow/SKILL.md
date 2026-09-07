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
  - `plan` — no plan comment exists yet on this issue
  - `iterate` — bot has posted a plan; there are new user comments since the last plan comment
  - `implement` — issue is in the Implement column
  - `done` — all PRs linked to the issue are approved; merge them and wrap up

If not provided directly, run:
```bash
gh issue view <N> -R <repo> --json number,title,body,comments
```

## Phase 2.5: Marker sentinels — load-bearing

Every action posts a **start** comment before it works and a **finish** comment when it is done. Each carries an HTML-comment sentinel **as the first line of the body**, with nothing before it:

| Sentinel | Posted by |
|---|---|
| `<!-- pf:plan-started -->` | `plan` and `iterate`, first step |
| `<!-- pf:plan-finished -->` | the plan comment / the iterate response |
| `<!-- pf:implement-started -->` | `implement`, first step |
| `<!-- pf:implement-finished -->` | the implementation-complete comment |
| `<!-- pf:done-started -->` | `done`, first step |
| `<!-- pf:done-finished -->` | the completion summary |

`project-monitor` reads these to decide whether a card is already in flight (`in_flight_state()` in `scripts/project-monitor`). It matches them on the **first line only**, which is what keeps a plan comment from blocking its own card by quoting a marker in its prose.

⚠ These six lines are dispatch state, not decoration. Do not reorder them, do not put text above them, and do not change a sentinel string without changing the matching constant in `scripts/project-monitor`. Never write a sentinel into a plan or a summary body — it will be read as a state change.

## Phase 3: Execute

### Action: plan

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "<!-- pf:plan-started -->
## Planning

Reading the issue and drafting a plan now."
```

2. Read the issue title and body. Create a thorough implementation plan and post it as a comment:

```bash
gh issue comment <N> -R <repo> --body "<!-- pf:plan-finished -->
## Plan

<detailed plan covering:
- What will be implemented and why
- Step-by-step approach
- Files to be created or modified
- Open questions or decisions needing input>

---
*Waiting for your feedback. Move the card to **Implement** when you're ready to proceed.*"
```

### Action: iterate

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "<!-- pf:plan-started -->
## Reviewing feedback

Reading your comments and updating the plan now."
```

2. Read the full comment thread:
```bash
gh issue view <N> -R <repo> --json comments
```

3. Understand the user's latest feedback. Post a refined response — update the plan, answer questions, or confirm the approach:

```bash
gh issue comment <N> -R <repo> --body "<!-- pf:plan-finished -->
<response to feedback>"
```

If the plan is solid and no changes are needed, end with:
```
---
*Plan looks good. Move the card to **Implement** when you're ready.*
```

### Action: implement

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "<!-- pf:implement-started -->
## Starting implementation

Beginning work now. I will open PRs when complete."
```

2. **Read the plan** from the issue comment thread (latest bot comment starting with `<!-- pf:plan-finished -->` or `## Plan`).

3. **Check for a previous run's leftovers before touching git.** A run that died mid-implementation is retried after an hour, so a branch, commits, or even a PR may already exist. Resume from whatever is there rather than duplicating it:
```bash
git -C <repo path> fetch origin
git -C <repo path> branch -a --list '*feat/issue-<N>-*'
gh pr list -R <repo> --state open --search "<N> in:body" --json number,headRefName,url
```
   - **Open PR already exists** → check out its `headRefName`, finish any unfinished work per the plan, push to the same branch, and skip step 5's `gh pr create`. Reuse the existing PR.
   - **Branch exists, no PR** → `git checkout <branch>` (add `git pull origin <branch>` if it has a remote) and continue on it.
   - **Neither** → create it: `git checkout -b feat/issue-<N>-<short-description>`

4. **Implement** in the local repo clone (find the path using `repos.root` from config):
   - Make all changes per the plan
   - Update `CONTEXT.md` (and `README.md` if applicable) in each affected repo to reflect what changed — so the context diff is visible in the PR alongside the code
   - Commit everything together with descriptive messages

5. **Open PR(s)** — include `Closes #<N>` in the body. Always include a `## Post-merge` section — even when there is nothing to do. Never omit the section. The two valid forms are mutually exclusive — never mix them:

   **CASE A — no post-merge actions needed:** write one explanatory sentence, no bullet points:
   ```
   ## Post-merge
   No post-merge actions required — changes are self-contained within the repo and take effect after merge without any restart, pull, or deploy steps.
   ```

   **CASE B — post-merge actions exist:** list them as bullet points, no "no actions" sentence:
   ```
   ## Post-merge
   - pull: `~/repos/project-flow` `~/repos/infra`
   - run: `<shell command, e.g. docker restart homeassistant>`
   ```

   ⚠ Self-check before opening the PR: if the `## Post-merge` section contains any bullet points or commands, it must NOT also contain a "no post-merge actions" sentence.

```bash
gh pr create -R <repo> \
  --title "<title>" \
  --body "Closes #<N>

## Summary
<what was implemented>

## Post-merge
<CASE A or CASE B content — never both>"
```

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

6. **Move card to In Review** via GraphQL mutation (use values from config.yaml):
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

7. **Post summary comment** with PR links:
```bash
gh issue comment <N> -R <repo> --body "<!-- pf:implement-finished -->
## Implementation complete

PRs opened:
- <PR URL>

The card has been moved to In Review."
```

### Action: done

All PRs linked to the issue are approved. Squash-merge them, update all repos, run post-merge steps, and close out the card.

1. **Signal start:**
```bash
gh issue comment <N> -R <repo> --body "<!-- pf:done-started -->
## Merging PRs

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
gh issue comment <N> -R <repo> --body "<!-- pf:done-finished -->
## Done

All PRs squash-merged, branches deleted, repos pulled to latest main.

The card has been moved to Done."
```

## Phase 4: Confirm

Report what was done in one concise sentence. No approval needed.

## Automated driver

This skill is designed to be invoked by `project-monitor` (at `project-flow/scripts/project-monitor`), which polls the GitHub Project board, detects when cards move between columns, and dispatches Claude with the appropriate action (`plan`, `iterate`, `implement`, or `done`). You can also invoke it manually ("plan issue #N", "implement issue #N").
