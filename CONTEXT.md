# Context: skills

AI-optimized briefing for this repository. Kept current by the `context-update` skill after meaningful changes.

## Purpose

Public Claude Code plugin (`sv-skills`) for a single developer. Automates the development workflow — particularly the PR review loop — and will grow to capture other repeatable Claude Code workflows over time.

## Current state

- **Three skills implemented:** `pr-workflow` (create PR with rich context), `context-update` (maintain CONTEXT.md and README.md), and `project-workflow` (handle `plan`, `iterate`, `implement`, and `done` actions for kanban issues).
- **No commands or agents yet.** `commands/` and `agents/` are empty placeholders.
- Plugin is installed locally via `claude plugin marketplace add ~/repos/skills`.
- Repo is public on GitHub at `svsomething/skills`.
- `svsomething-bot` is a separate GitHub account used for all bot-posted comments and GraphQL mutations — needed because PR authors can't approve their own PRs.

## Key decisions

- **Repo doubles as a marketplace.** Root `.claude-plugin/marketplace.json` lists the plugin; actual plugin content lives under `plugins/sv-skills/`. This is required by the Claude Code plugin install mechanism — `"source": "."` is not supported; plugins must be in a subdirectory.
- **Public repo.** Skills are general-purpose workflow automation, nothing sensitive.
- **Mixed structure** (plugin + docs/experiments). `docs/` holds authoring guides and an experiments log alongside the plugin content.
- **`author` field must be an object** in `plugin.json` — `{"name": "..."}`, not a plain string. The validator rejects a string.
- **Mini-agentic kanban** drives autonomous issue handling. GitHub Project #1 (`svsomething/skills`) is the board. `project-monitor` in infra polls it, dispatches Claude with plan/implement actions, and `project-workflow` executes them. The bot account posts plans as comments; the user moves cards to signal approval.

## Plugin install flow

```
claude plugin marketplace add ~/repos/skills   # registers local marketplace
claude plugin install sv-skills                # installs from it
claude plugin marketplace update sv-skills     # picks up new skills after commits
```

## Skill authoring conventions

- Frontmatter: `name`, `description` (trigger-matching sentence), `tools`
- Body: phased workflow (Phase 1, Phase 2, …)
- Reference files in `skills/<name>/references/`
- Description is the primary trigger signal — be specific: "Use when user says X or Y"

## Relationships

- [`infra`](https://github.com/svsomething/infra) — two scripts are the other halves of the automation loops:
  - `pr-monitor` (at `infra/scripts/pr-monitor`) polls open PRs, detects new review comments, and dispatches Claude with inline prompts to address them (does not use the `pr-workflow` skill)
  - `project-monitor` (at `infra/scripts/project-monitor`) polls GitHub Project #1, detects `plan`/`iterate`/`implement`/`done` actions, and dispatches Claude via `project-workflow`

## What to watch for

- After adding a new skill, remind the user to run `claude plugin marketplace update sv-skills`.
- The `docs/README.md` experiments log should be updated when a skill approach is validated or rejected.
- Keep this CONTEXT.md current — it's the primary briefing for Claude web when discussing new skills to build.
