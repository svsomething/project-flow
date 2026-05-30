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
| [context-update](plugins/sv-skills/skills/context-update/SKILL.md) | "update context", or after a meaningful merge | Rewrites `CONTEXT.md` and `README.md` in the current repo to reflect recent changes |
| [project-workflow](plugins/sv-skills/skills/project-workflow/SKILL.md) | "plan issue", "implement issue", or dispatched by project-monitor | Handles one kanban action (plan or implement) for a GitHub issue on the project board |

## PR review workflow

This plugin powers a full human-in-the-loop review loop:

1. Discuss a change with Claude → agree on a plan
2. Claude implements on a feature branch and opens a PR (via `pr-workflow`)
3. Review and comment on GitHub — Claude addresses comments automatically (via `pr-monitor` cron)
4. Approve the PR → auto-merged to main

The `pr-monitor` cron script lives in [infra/scripts/pr-monitor](https://github.com/svsomething/infra/blob/main/scripts/pr-monitor).

## Kanban workflow

Issues on [GitHub Project #1](https://github.com/users/svsomething/projects/1) drive a second automation loop:

1. Create an issue and move it to **Plan** — `project-monitor` detects this and dispatches Claude
2. Claude posts a plan as a bot comment (via `project-workflow`) — the card moves to **Waiting**
3. Review the plan and comment with feedback — `project-monitor` dispatches Claude to iterate
4. Move the card to **Implement** — `project-monitor` dispatches Claude to implement
5. Claude opens PRs, moves the card to **In Review**, and posts a summary comment
6. Approve the PRs → auto-merged; move card to **Done**

The `project-monitor` cron script lives in [infra/scripts/project-monitor](https://github.com/svsomething/infra/blob/main/scripts/project-monitor).

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
