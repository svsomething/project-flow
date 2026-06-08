# Context: project-flow

AI-optimized briefing for this repository. Kept current by the `context-update` skill after meaningful changes.

## Purpose

Public, standalone Claude Code plugin and automation runtime for a mini-agentic software development workflow. Anyone can fork this repo to get a GitHub Project kanban board that automatically plans, implements, and reviews issues using Claude Code.

Previously named `svsomething/skills`.

## Current state

- **Three skills:** `pr-workflow` (create PR with rich context), `context-update` (maintain CONTEXT.md and README.md), and `project-workflow` (handle `plan`, `iterate`, `implement`, and `done` actions for kanban issues).
- **Two cron scripts:** `scripts/project-monitor` (polls GitHub Project board, dispatches Claude) and `scripts/pr-monitor` (polls open PRs, addresses review comments, auto-merges approved PRs).
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
- **PID-aware lock files.** Both monitors write their PID to the lock file and check liveness on startup. Stale locks from crashes are cleared automatically rather than blocking all future runs.

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
