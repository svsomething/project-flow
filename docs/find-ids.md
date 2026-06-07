# Finding your GitHub Project IDs

GitHub Project v2 uses opaque GraphQL node IDs that aren't visible in the UI. Run these queries to get the values needed for `config.yaml`.

## Prerequisites

```bash
# Authenticate as your primary account (not the bot)
gh auth status
```

## Query 1: Get project.id and project.status_field_id

Replace `YOUR_USERNAME` and `PROJECT_NUMBER` with your values.

```bash
gh api graphql -f query='
{
  user(login: "YOUR_USERNAME") {
    projectV2(number: PROJECT_NUMBER) {
      id
      fields(first: 20) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
        }
      }
    }
  }
}'
```

**What to look for in the output:**

- `data.user.projectV2.id` → this is `project.id` (looks like `PVT_kwHO...`)
- In `fields.nodes`, find the field with `"name": "Status"`:
  - `id` → this is `project.status_field_id` (looks like `PVTSSF_lAH...`)
  - Each entry in `options` is one of your columns — the `id` is the 8-char hex value for `project.columns.*`

**Example output (abbreviated):**

```json
{
  "data": {
    "user": {
      "projectV2": {
        "id": "PVT_kwHOERrops4BZOd2",
        "fields": {
          "nodes": [
            {
              "id": "PVTSSF_lAHOERrops4BZOd2zhUOqxg",
              "name": "Status",
              "options": [
                { "id": "d7e1fd51", "name": "Plan" },
                { "id": "61e4505c", "name": "Implement" },
                { "id": "df73e18b", "name": "In Review" },
                { "id": "98236657", "name": "Done" }
              ]
            }
          ]
        }
      }
    }
  }
}
```

Map the option IDs to `config.yaml`:

```yaml
project:
  id: PVT_kwHOERrops4BZOd2               # from projectV2.id
  status_field_id: PVTSSF_lAHOERrops4BZOd2zhUOqxg  # from Status field id
  columns:
    plan:      d7e1fd51   # from options where name == "Plan"
    implement: 61e4505c   # from options where name == "Implement"
    in_review: df73e18b   # from options where name == "In Review"
    done:      98236657   # from options where name == "Done"
```

## Letting Claude fill this in for you

Open a Claude Code session in this repo and paste:

> "Read docs/find-ids.md, run Query 1 against my project (number N, owner myusername), and fill the results into config.yaml."

Claude will run the query and write the values for you.
