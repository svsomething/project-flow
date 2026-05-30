---
name: context-update
description: Update CONTEXT.md in the current repo to reflect recent changes. Use when the user says "update context", "refresh context", or after a meaningful change is merged (new service, new skill, architecture decision, significant refactor).
tools: Read, Bash, Edit, Write
---

# Context Update

Keep `CONTEXT.md` accurate and useful for AI assistants (Claude web, Claude Code in a fresh session).

## Phase 1: Understand what changed

1. Read the current `CONTEXT.md` (if it exists)
2. Get recent history:
   ```bash
   git log --oneline -20
   git diff HEAD~5..HEAD --stat
   ```
3. If triggered after a specific PR merge, read that PR:
   ```bash
   gh pr view <N> --json title,body,files
   ```
4. Scan for structural changes:
   ```bash
   ls -la
   find . -name "*.md" -not -path "./.git/*" | head -20
   ```

## Phase 2: Identify what needs updating

Compare current `CONTEXT.md` against actual repo state. Flag sections that are:
- **Stale** — describe things that no longer exist or have changed
- **Missing** — meaningful new things not yet captured
- **Inaccurate** — decisions or state that have evolved

Focus on:
- **Current state** — what exists now, what's empty/placeholder vs real
- **Key decisions** — new architectural or design choices made
- **Conventions** — any new patterns established
- **Relationships** — new dependencies or integrations with other repos
- **What to watch for** — gotchas or constraints a fresh AI should know

## Phase 3: Rewrite affected sections

Edit `CONTEXT.md` in place — update only the sections that changed. Preserve sections that are still accurate.

Rules for good CONTEXT.md content:
- Write for a smart AI with no prior context, not for a human reader
- Prioritize the WHY behind decisions, not just the WHAT
- Capture things that aren't derivable from reading the code (constraints, history, intent)
- Be dense — no introductory fluff, no headers that restate the obvious
- Current state should always reflect reality, not aspirations

## Phase 4: Confirm

Show a brief diff summary of what changed in `CONTEXT.md` and why. Don't ask for approval — just report what was updated and flag anything uncertain.
