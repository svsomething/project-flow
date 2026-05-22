# skills

Personal [Claude Code](https://claude.ai/code) plugin — custom skills, commands, and agents.

## Install

Clone and register the local marketplace, then install:

```bash
git clone git@github.com:svsomething/skills.git ~/repos/skills
claude plugin marketplace add ~/repos/skills
claude plugin install sv-skills
```

## Directory layout

```
skills/
├── .claude-plugin/
│   ├── marketplace.json          # Marketplace manifest (lists plugins in this repo)
│   └── plugin.json               # Top-level plugin identity (unused at runtime)
├── plugins/
│   └── sv-skills/                # The actual installable plugin
│       ├── .claude-plugin/
│       │   └── plugin.json       # Plugin manifest
│       ├── skills/               # Skills (triggered automatically or via /name)
│       ├── commands/             # Slash commands (user-invoked as /name)
│       └── agents/               # Sub-agents
└── docs/                         # Authoring guide, workflow notes, experiments
```

### skills/ vs commands/ vs agents/

| Type | File | Triggered by | Best for |
|------|------|-------------|----------|
| Skill | `plugins/sv-skills/skills/<name>/SKILL.md` | Claude automatically, or user types `/<name>` | Reusable multi-step workflows |
| Command | `plugins/sv-skills/commands/<name>.md` | User types `/<name>` | Quick user-initiated actions |
| Agent | `plugins/sv-skills/agents/<name>.md` | `claude --agent <name>` or spawned by skills | Specialized autonomous sub-agents |

## Authoring a skill

Create `plugins/sv-skills/skills/<name>/SKILL.md` with this frontmatter:

```yaml
---
name: my-skill
description: One sentence. Use when user asks X, mentions Y, or Z occurs.
tools: Read, Bash, Edit, Write
---
```

Then write the body as a phased workflow (Phase 1, Phase 2, …).  
Reference files go in `plugins/sv-skills/skills/<name>/references/`.

See `docs/README.md` for the full authoring guide.
