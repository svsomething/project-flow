# Setup guide

This guide walks you through setting up project-flow from scratch.

## Prerequisites

- **Claude Code** — install from [claude.ai/code](https://claude.ai/code)
- **GitHub CLI** — install from [cli.github.com](https://cli.github.com), then run `gh auth login`
- **Python 3.8+** with PyYAML: `pip install pyyaml`
- **An always-on Linux machine** to run the cron jobs (home server, Raspberry Pi, VPS, etc.)
- **Two GitHub accounts**: your primary account, plus a bot account for posting automated comments

## Step 1: Create a bot GitHub account

The bot account posts plans, implementation summaries, and status updates as comments. A separate account is required because GitHub doesn't allow PR authors to approve their own PRs — the bot posts so your primary account can approve.

1. Create a new GitHub account (e.g. `yourname-bot`)
2. In the bot account, go to **Settings → Developer settings → Personal access tokens → Tokens (classic)**
3. Generate a new token with these scopes: `repo`, `project`
4. Save the token to a file on your machine:
   ```bash
   echo "ghp_your_token_here" > ~/.config/bot-gh-token
   chmod 600 ~/.config/bot-gh-token
   ```

## Step 2: Create a GitHub Project

1. Go to your GitHub profile → **Projects → New project**
2. Choose **Board** layout
3. Create four columns (in this order): **Plan**, **Implement**, **In Review**, **Done**
4. Note the project URL — it will be `github.com/users/<yourname>/projects/<number>`

## Step 3: Fork and clone project-flow

```bash
# Fork svsomething/project-flow on GitHub, then:
git clone git@github.com:<yourname>/project-flow.git ~/repos/project-flow
```

## Step 4: Fill in config.yaml

Open `config.yaml` at the repo root. Every key has an inline comment explaining what it is.

The trickiest part is the GraphQL IDs (`project.id`, `project.status_field_id`, `project.columns.*`). These aren't visible in the GitHub UI. Run the queries in **[docs/find-ids.md](find-ids.md)** to get them — each query takes about 30 seconds.

Once you have the IDs, fill them into `config.yaml`. A Claude prompt that makes this easy:

> "Read docs/find-ids.md, run the GraphQL queries against my project (number N, owner myname), and fill the results into config.yaml."

## Step 5: Install the Claude Code plugin

```bash
claude plugin marketplace add ~/repos/project-flow
claude plugin install sv-skills
```

To pick up new skills after future commits:
```bash
claude plugin marketplace update sv-skills
```

## Step 6: Install the cron jobs

Run `crontab -e` and add:

```
PATH=/home/<yourname>/.npm-global/bin:/usr/local/bin:/usr/bin:/bin
* * * * * python3 /home/<yourname>/repos/project-flow/scripts/project-monitor >> /home/<yourname>/.claude/project-monitor.log 2>&1
* * * * * python3 /home/<yourname>/repos/project-flow/scripts/pr-monitor >> /home/<yourname>/.claude/pr-monitor.log 2>&1
```

The `PATH` line ensures the `claude` binary is visible to cron.

## Step 7: Verify

Check the logs after a minute or two:
```bash
tail -f ~/.claude/project-monitor.log
tail -f ~/.claude/pr-monitor.log
```

Both should log "No active items" / "No GitHub repos found" (or similar) without errors.

## Day-to-day usage

**Kanban flow:**
1. Create a GitHub issue and move it to **Plan**
2. Claude posts a plan comment within ~1 minute
3. Comment with feedback; Claude iterates
4. When satisfied, move the card to **Implement**
5. Claude implements, opens PRs, moves card to **In Review**
6. Review and approve the PRs on GitHub
7. Claude detects approval, squash-merges, and moves card to **Done**

**PR review flow:**
1. Claude implements on a feature branch (or you open a branch manually)
2. Register the PR with the monitor by running the snippet at the end of the `pr-workflow` skill
3. Leave inline review comments on GitHub
4. Claude addresses comments and replies "Addressed in \<SHA\>" within ~1 minute
5. Approve the PR → Claude auto-merges it

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `PyYAML not installed` error | Run `pip install pyyaml` |
| `config.yaml not found` | Check that `scripts/project-monitor` is running from the right location |
| GraphQL errors | Verify `project.id` and `project.status_field_id` in config.yaml |
| Bot token errors | Check `~/.config/bot-gh-token` exists and has the right scopes |
| Claude not invoked | Check that `claude` is on the PATH in crontab (add `PATH=...` line) |
| Lock file stuck | `rm ~/.claude/project-monitor.lock ~/.claude/pr-monitor.lock` |
