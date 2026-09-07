# project-flow

A self-contained, forkable workflow for AI-assisted software development using [Claude Code](https://claude.ai/code) and GitHub Projects.

Fork this repo, fill in `config.yaml`, and get a kanban board that automatically plans, implements, and reviews your issues.

<p align="center">
  <img src="https://github.com/user-attachments/assets/2b5f1ea9-53e5-4ef2-8afe-96bb222c9493" alt="project-flow kanban board" width="900" />
</p>

*The mini-agentic project board — cards move automatically from Plan → Implement → In Review → Done as Claude works through each issue.*

## What's included

| Component | What it does |
|-----------|-------------|
| [skills/project-workflow](plugins/sv-skills/skills/project-workflow/SKILL.md) | Plans, iterates, implements, and closes GitHub issues on the project board |
| [skills/pr-workflow](plugins/sv-skills/skills/pr-workflow/SKILL.md) | Creates feature branches, commits, pushes, and opens a GitHub PR with rich context |
| [skills/context-update](plugins/sv-skills/skills/context-update/SKILL.md) | Keeps `CONTEXT.md` and `README.md` accurate after meaningful changes |
| [scripts/project-monitor](scripts/project-monitor) | Cron script — polls the GitHub Project board and dispatches Claude for each active card |
| [scripts/pr-monitor](scripts/pr-monitor) | Cron script — polls open PRs, addresses review comments, auto-merges approved PRs |
| [scripts/claude_runner.py](scripts/claude_runner.py) | Shared by both monitors — invokes the Claude CLI with a timeout, detects failures, and flags broken credentials on the card |

## Quickstart

See [docs/setup.md](docs/setup.md) for the full walkthrough. The short version:

1. Fork this repo and clone it locally
2. Fill in `config.yaml` (see inline comments; run the queries in `docs/find-ids.md` to get the GraphQL IDs)
3. Install the Claude Code plugin:
   ```bash
   claude plugin marketplace add ~/repos/project-flow
   claude plugin install sv-skills
   ```
4. Add the cron jobs:
   ```
   * * * * * python3 ~/repos/project-flow/scripts/project-monitor >> ~/.claude/project-monitor.log 2>&1
   * * * * * python3 ~/repos/project-flow/scripts/pr-monitor >> ~/.claude/pr-monitor.log 2>&1
   ```
5. Create a GitHub Project with columns: Plan → Implement → In Review → Done

## How the kanban workflow operates

1. Create a GitHub issue and move it to **Plan** — `project-monitor` detects this and dispatches Claude
2. Claude posts a plan as a bot comment (via `project-workflow`) — you review and comment with feedback
3. `project-monitor` dispatches Claude to iterate until you're satisfied
4. Move the card to **Implement** — `project-monitor` dispatches Claude to implement
5. Claude opens PRs, moves the card to **In Review**, and posts a summary comment
6. Approve the PRs → `project-monitor` detects all approvals and dispatches the `done` action
7. Claude squash-merges all PRs, updates context, and moves the card to **Done**

Mention "opus", "sonnet", or "haiku" anywhere in the issue body to run that card's entire lifecycle (plan/iterate/implement/done) on that model — no fixed syntax needed, natural phrasing like "please use Opus for this one" works. If more than one alias appears, the first mention wins.

## How the PR review workflow operates

1. Claude implements a change and opens a PR (via `pr-workflow`)
2. Review and leave comments on GitHub
3. `pr-monitor` detects new inline review comments and dispatches Claude to address them
4. Claude commits fixes and replies "Addressed in \<SHA\>"
5. Once approved, `pr-monitor` auto-squash-merges the PR

## When Claude can't authenticate

The monitors run unattended, so a failed invocation has to announce itself rather than retry silently.

1. Both monitors invoke Claude through `scripts/claude_runner.py`, which enforces a 30-minute timeout and inspects the captured output. Any failure logs a line starting with `ERROR:` — `grep 'ERROR:' ~/.claude/project-monitor.log` tells you at a glance whether things are working.
2. If the output looks like a credential failure, a circuit breaker opens (`~/.claude/claude-auth-state.json`). Further invocations are skipped with `SKIP: Claude auth broken since <ts>` instead of failing once a minute.
3. The bot comments **⚠️ Claude authentication required** on the affected card. The bot's GitHub token is separate from Claude's credentials, so this still works while Claude auth is dead.

Run `claude` on the host and re-authenticate. Every 15 minutes one invocation is let through as a probe; on success the breaker clears, the log says `RECOVERED`, the bot replies on the card, and work resumes with no action from you. Cards never change columns because of an auth outage. To resume immediately, delete `~/.claude/claude-auth-state.json`.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

## Prerequisites

- [Claude Code](https://claude.ai/code) installed and configured
- [GitHub CLI (`gh`)](https://cli.github.com/) authenticated
- Python 3.8+ with PyYAML: `pip install pyyaml`
- A GitHub account + a separate bot account (for posting plans and mutations)
- An always-on machine to run the cron jobs (Linux server, Raspberry Pi, etc.)

## Directory layout

```
project-flow/
├── config.yaml                    # Fill this in — all deployment-specific values
├── CONTEXT.md                     # AI briefing for this repo
├── docs/
│   ├── README.md                  # Skill authoring guide
│   ├── setup.md                   # Step-by-step setup for new adopters
│   └── find-ids.md                # GraphQL queries to discover Project/field IDs
├── scripts/
│   ├── project-monitor            # Cron: polls project board, dispatches Claude
│   ├── pr-monitor                 # Cron: polls PRs, addresses comments, auto-merges
│   └── claude_runner.py           # Shared: hardened Claude CLI wrapper + auth breaker
├── tests/
│   └── test_claude_runner.py      # python3 -m unittest discover -s tests
└── plugins/
    └── sv-skills/
        ├── .claude-plugin/
        │   └── plugin.json
        └── skills/
            ├── project-workflow/  # Kanban driver skill
            ├── pr-workflow/       # PR creation skill
            └── context-update/    # CONTEXT.md maintenance skill
```

## Adding a skill

1. `mkdir plugins/sv-skills/skills/<name>`
2. Create `SKILL.md` — see [docs/README.md](docs/README.md) for the frontmatter spec
3. Commit and run `claude plugin marketplace update sv-skills`
