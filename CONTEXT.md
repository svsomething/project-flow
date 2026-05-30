# Context: skills

AI-optimized briefing for this repository. Kept current by the `context-update` skill after meaningful changes.

## Purpose

Public Claude Code plugin (`sv-skills`) for a single developer. Automates the development workflow — particularly the PR review loop — and will grow to capture other repeatable Claude Code workflows over time.

## Current state

- **Two skills implemented:** `pr-workflow` (create PR with rich context) and `context-update` (maintain CONTEXT.md files).
- **No commands or agents yet.** `commands/` and `agents/` are empty placeholders.
- Plugin is installed locally via `claude plugin marketplace add ~/repos/skills`.
- Repo is public on GitHub at `svsomething/skills`.

## Key decisions

- **Repo doubles as a marketplace.** Root `.claude-plugin/marketplace.json` lists the plugin; actual plugin content lives under `plugins/sv-skills/`. This is required by the Claude Code plugin install mechanism — `"source": "."` is not supported; plugins must be in a subdirectory.
- **Public repo.** Skills are general-purpose workflow automation, nothing sensitive.
- **Mixed structure** (plugin + docs/experiments). `docs/` holds authoring guides and an experiments log alongside the plugin content.
- **`author` field must be an object** in `plugin.json` — `{"name": "..."}`, not a plain string. The validator rejects a string.

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

- [`infra`](https://github.com/svsomething/infra) — the `pr-monitor` cron script (at `infra/scripts/pr-monitor`) is the other half of the PR workflow loop that `pr-workflow` skill initiates.

## What to watch for

- After adding a new skill, remind the user to run `claude plugin marketplace update sv-skills`.
- The `docs/README.md` experiments log should be updated when a skill approach is validated or rejected.
- Keep this CONTEXT.md current — it's the primary briefing for Claude web when discussing new skills to build.
