# skills

Personal [Claude Code](https://claude.ai/code) plugin — custom skills, commands, and agents for automating development workflows.

## Install

```bash
git clone git@github.com:svsomething/skills.git ~/repos/skills
claude plugin marketplace add ~/repos/skills
claude plugin install sv-skills
```

## What's included

| Skill | Trigger | What it does |
|-------|---------|--------------|
| [pr-workflow](plugins/sv-skills/skills/pr-workflow/SKILL.md) | "submit as PR", "open a PR", "push for review" | Creates a feature branch, commits, pushes, opens a GitHub PR with rich context |
| [context-update](plugins/sv-skills/skills/context-update/SKILL.md) | "update context", or after a meaningful merge | Rewrites `CONTEXT.md` in the current repo to reflect recent changes |

## PR review workflow

This plugin powers a full human-in-the-loop review loop:

1. Discuss a change with Claude → agree on a plan
2. Claude implements on a feature branch and opens a PR (via `pr-workflow`)
3. Review and comment on GitHub — Claude addresses comments automatically (via `pr-monitor` cron)
4. Approve the PR → auto-merged to main

The `pr-monitor` cron script lives in [infra/scripts/pr-monitor](https://github.com/svsomething/infra/blob/main/scripts/pr-monitor).

## Directory layout

```
skills/
├── .claude-plugin/
│   ├── marketplace.json          # Lists this repo as a marketplace
│   └── plugin.json               # Top-level plugin identity
├── plugins/
│   └── sv-skills/
│       ├── .claude-plugin/
│       │   └── plugin.json       # Plugin manifest (name, version, author)
│       ├── skills/               # Skills — triggered automatically or via /name
│       ├── commands/             # Slash commands — user-invoked as /name
│       └── agents/               # Sub-agents
└── docs/
    └── README.md                 # Authoring guide and frontmatter reference
```

## Adding a skill

1. `mkdir plugins/sv-skills/skills/<name>`
2. Create `SKILL.md` — see [docs/README.md](docs/README.md) for the frontmatter spec
3. Commit and run `claude plugin marketplace update sv-skills`

## Related

- [infra](https://github.com/svsomething/infra) — home server infrastructure and dotfiles
- [Claude Code docs](https://docs.claude.ai/code)
