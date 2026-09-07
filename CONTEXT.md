# Context: project-flow

AI-optimized briefing for this repository. Kept current by the `context-update` skill after meaningful changes.

## Purpose

Public, standalone Claude Code plugin and automation runtime for a mini-agentic software development workflow. Anyone can fork this repo to get a GitHub Project kanban board that automatically plans, implements, and reviews issues using Claude Code.

Previously named `svsomething/skills`.

## Current state

- **Three skills:** `pr-workflow` (create PR with rich context), `context-update` (maintain CONTEXT.md and README.md), and `project-workflow` (handle `plan`, `iterate`, `implement`, and `done` actions for kanban issues).
- **Two cron scripts:** `scripts/project-monitor` (polls GitHub Project board, dispatches Claude) and `scripts/pr-monitor` (polls open PRs, addresses review comments, auto-merges approved PRs). Both invoke Claude through the shared `scripts/claude_runner.py`.
- **One shared module:** `scripts/claude_runner.py` — hardened Claude CLI wrapper (timeout, exit-code and auth-failure detection, circuit breaker, GitHub notification).
- **Tests:** `tests/test_claude_runner.py`, plain `unittest`, no extra dependencies. Run with `python3 -m unittest discover -s tests`.
- **One config file:** `config.yaml` at repo root (gitignored) — all deployment-specific values. Copy from `config.yaml.example` and fill in once; scripts and skills read it at runtime.
- Plugin installed locally via `claude plugin marketplace add ~/repos/project-flow`.
- Repo is public at `svsomething/project-flow`.
- `svsomething-bot` is a separate GitHub account used for all bot-posted comments and GraphQL mutations — required because PR authors can't approve their own PRs.

## Key decisions

- **Repo doubles as a marketplace.** Root `.claude-plugin/marketplace.json` lists the plugin; actual plugin content lives under `plugins/sv-skills/`. Required by the Claude Code plugin install mechanism — `"source": "."` is not supported; plugins must be in a subdirectory.
- **config.yaml drives all deployment-specific values.** Scripts (`project-monitor`, `pr-monitor`) load `config.yaml` via PyYAML at startup. The `project-workflow` skill reads it at runtime by running `cat ~/repos/project-flow/config.yaml` before executing any GraphQL mutations. No hardcoded IDs anywhere.
- **CONTEXT.md is updated as part of the PR, not after merge.** Both `pr-workflow` and `project-workflow` (implement action) update CONTEXT.md before committing, so the context diff is visible during review alongside the code changes.
- **Scripts moved from infra.** `project-monitor` and `pr-monitor` were in `svsomething/infra`. Moved here so the whole workflow ships as one self-contained repo.
- **config.yaml is gitignored; config.yaml.example ships instead.** Keeps personal org/project IDs out of the public repo. Forks start from the example and fill in their own values.
- **Owner-only access control throughout.** All autonomous triggers (iterate, comment-address, approve-to-merge) require the acting user to be `github.org` (the owner login). Enforced in `project-monitor` (iterate gate) and `pr-monitor` (comment and approval checks).
- **Tracked-PR gate in pr-monitor.** Comment-addressing and auto-merge only run on PRs registered in the state file (opened by the bot via project-workflow). Prevents Claude from touching PRs opened by other contributors.
- **Auto-registration of bot PRs in pr-monitor.** Each scan cycle, before the per-PR action loop, pr-monitor fetches the `author` field from `gh pr list` and calls `add_to_state()` for any open PR whose author is the bot. This makes state tracking self-healing: PRs opened by the bot (via project-workflow or manually) are picked up on the next poll even if they weren't registered at creation time.
- **Immediate registration in project-workflow.** After `gh pr create` in the `implement` action, the skill appends the new PR to `~/.claude/pr-monitor-state.json` so monitoring begins before the next pr-monitor poll cycle.
- **Mandatory `## Post-merge` section in all PRs.** Both `project-workflow` (implement action) and `pr-workflow` always include a `## Post-merge` section in the PR body. When there are no post-merge steps, free-form prose explains why. The section is never omitted — this prevents silent failures where required post-merge steps are accidentally skipped.
- **PID-aware lock files.** Both monitors write their PID to the lock file and check liveness on startup. Stale locks from crashes are cleared automatically rather than blocking all future runs.
- **Fail-loud Claude invocation.** Both monitors call `claude_runner.run_claude()` instead of a bare `subprocess.run(...)` whose result was discarded. Every non-`OK` outcome logs a line starting with `ERROR:` and returns a status (`OK` / `AUTH_FAILED` / `FAILED` / `TIMEOUT` / `SKIPPED`) that the caller acts on. Before this, a total failure logged the same `Invoking Claude` line as a success and retried silently every minute (16 wasted cycles in the 2026-06-22 incident).
- **Auth detection does not trust the exit code alone.** `run_claude` matches a list of credential-failure signatures in the *captured output* and independently treats a non-zero exit and a timeout as failures. It therefore fires whether the CLI exits 1, exits 0, or hangs — the CLI's behaviour on an expired credential could not be pinned down, so the detector does not depend on it. The signature list is a heuristic: if the CLI's wording changes, a future auth failure falls through to the generic `FAILED` path — still loud, just without the auth-specific comment.
- **Auth circuit breaker.** State in `~/.claude/claude-auth-state.json`, shared by both monitors. Once `AUTH_FAILED` is recorded they skip invoking Claude entirely and log `SKIP: Claude auth broken since <ts>` — every invocation while credentials are dead is guaranteed to fail. Every `AUTH_RETRY_INTERVAL` (900s) one invocation is let through as a live probe; success clears the state and logs `RECOVERED`. Board and PR polling keep running normally — they use the bot's `GH_TOKEN`, which is unaffected.
- **Auth failures are flagged on the card.** The bot's GitHub token is independent of Claude's credentials, so commenting still works when Claude auth is dead. On the first `AUTH_FAILED` the bot posts a `## ⚠️ Claude authentication required` comment on the issue (project-monitor) or PR (pr-monitor), deduped via the `notified` list in the breaker state plus a scan of existing bot comments. On recovery it replies `## ✅ Claude authentication restored` on every alerted card and clears the state, so a future outage can notify again. The card deliberately does not change columns — leaving it in place is what lets work resume automatically.
- **Alert-marker scan is anchored.** The duplicate-alert check matches only comments that *start with* the alert heading. Unanchored substring guards elsewhere in `project-monitor` (see #30) have blocked cards whose plan merely quoted a marker phrase; new markers avoid repeating that.
- **Claude output is captured, not streamed.** `run_claude` uses `capture_output=True` so it can inspect the text, then re-emits it to the log prefixed with `  claude| `. The log keeps everything it showed before, attributable and indented, but appears only when the invocation finishes rather than live.
- **Timeouts are enforced.** `TIMEOUT_SECONDS = 1800`. A hung `claude` used to hold the monitor's PID lock indefinitely and wedge *all* board processing, not just the one card.

## Config structure

```yaml
github:
  org:            # GitHub username or org (also used as owner login for access control)
  bot_login:      # Bot account login
  bot_token_file: # Path to bot token (classic token, repo + project scopes; chmod 600)
repos:
  root:           # Directory containing local repo clones
  project_flow:   # Path to this repo
  monitored:      # Optional list of repo names to scan (omit to scan all under root)
project:
  number:         # Project board number (from URL)
  id:             # Project node ID (PVT_...)
  status_field_id: # Status field node ID (PVTSSF_...)
  columns:        # 8-char hex option IDs for each column
    plan / implement / in_review / done
```

## Plugin install flow

```
claude plugin marketplace add ~/repos/project-flow   # registers local marketplace
claude plugin install sv-skills                      # installs from it
claude plugin marketplace update sv-skills           # picks up new skills after commits
```

## Skill authoring conventions

- Frontmatter: `name`, `description` (trigger-matching sentence), `tools`
- Body: phased workflow (Phase 1, Phase 2, …)
- Reference files in `skills/<name>/references/`
- Description is the primary trigger signal — be specific: "Use when user says X or Y"

## Relationships

- [`infra`](https://github.com/svsomething/infra) — home server infrastructure. The workflow scripts formerly lived there; now fully in this repo. Infra just runs Docker services and dotfiles.

## What to watch for

- After adding a new skill, remind the user to run `claude plugin marketplace update sv-skills`.
- The `docs/README.md` experiments log should be updated when a skill approach is validated or rejected.
- The crontab must point to `~/repos/project-flow/scripts/` (not the old infra path).
- `config.yaml` is gitignored — never commit it. `config.yaml.example` is the committed template.
- `config.yaml` is the source of truth for all IDs — never hardcode them in skills or scripts.
- `grep 'ERROR:\|SKIP:\|RECOVERED' ~/.claude/project-monitor.log` is the fast way to see whether the monitors are actually working. A run that logs `Invoking Claude` and nothing else is a success; anything broken says so explicitly.
- If both monitors go quiet and the log shows `SKIP: Claude auth broken since ...`, run `claude` on the host to re-authenticate. Work resumes on its own within ~15 minutes; deleting `~/.claude/claude-auth-state.json` resumes immediately.
- The crontab runs the scripts straight out of the working tree, so a checked-out feature branch is what cron executes. Keep `scripts/` importable on every branch.
