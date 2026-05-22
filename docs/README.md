# docs

Authoring guide, workflow notes, and experiments for this Claude Code plugin.

## Skill authoring quick reference

### Frontmatter fields

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | kebab-case, matches directory name |
| `description` | Yes | One sentence. Drives automatic trigger matching — be specific about *when* to use it |
| `tools` | Yes | Comma-separated list of tools the skill needs |
| `user-invocable` | No | Set `false` if Claude-only (background knowledge, not user-triggered) |
| `disable-model-invocation` | No | Set `true` for side-effect-only commands that shouldn't spawn Claude |

### Description writing tips

The description is the primary signal Claude uses to decide when to invoke the skill.  
Write it as: *"Use when user asks for X, mentions Y, or Z occurs."*

Be specific — vague descriptions cause unwanted triggering or missed triggers.

### Phase structure

Organize the skill body into numbered phases:

```markdown
## Phase 1: Gather context
...

## Phase 2: Analyse
...

## Phase 3: Report
...
```

### Reference files

Supporting docs, templates, and examples go in `skills/<name>/references/`.  
Link them in the skill body: `See [references/template.md]()`.

## Experiments log

<!-- Track experiments, learnings, and ideas here -->
| Date | Experiment | Outcome |
|------|-----------|---------|
