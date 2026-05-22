# skills

Personal [Claude Code](https://claude.ai/code) plugin — custom skills, commands, and agents.

## Install

```bash
claude plugin install github:svsomething/skills
```

Or clone and install locally:

```bash
git clone git@github.com:svsomething/skills.git ~/repos/skills
claude plugin install ~/repos/skills
```

## Directory layout

```
skills/
├── .claude-plugin/   # Plugin manifest
├── skills/           # Custom skills (invoked by Claude automatically or via /skill-name)
├── commands/         # Slash commands (invoked by user as /command-name)
├── agents/           # Custom agents
└── docs/             # Authoring notes, workflow docs, experiments
```

### skills/ vs commands/ vs agents/

| Type | File | Triggered by | Best for |
|------|------|-------------|----------|
| Skill | `skills/<name>/SKILL.md` | Claude automatically, or user types `/<name>` | Reusable multi-step workflows |
| Command | `commands/<name>.md` | User types `/<name>` | Quick user-initiated actions |
| Agent | `agents/<name>.md` | `claude --agent <name>` or spawned by skills | Specialized autonomous sub-agents |

## Authoring a skill

Create `skills/<name>/SKILL.md` with this frontmatter:

```yaml
---
name: my-skill
description: One sentence. Use when user asks X, mentions Y, or Z occurs.
tools: Read, Bash, Edit, Write
---
```

Then write the body as a phased workflow (Phase 1, Phase 2, …).  
Reference files go in `skills/<name>/references/`.

See `docs/README.md` for the full authoring guide.
