# scripts/

Org-level maintenance scripts for the `profit-trader` GitHub organization.

## update_repos.py

Updates repository descriptions and topics across the org from a central config file.

**Run (no install needed — requires [uv](https://docs.astral.sh/uv/)):**

```bash
export GITHUB_TOKEN=<token>   # fine-grained PAT: org repo metadata read/write

# Preview all changes
uv run scripts/update_repos.py --dry-run

# Apply all
uv run scripts/update_repos.py

# Apply to one repo
uv run scripts/update_repos.py --repo handbook
```

**Edit [`repo_config.yaml`](repo_config.yaml)** to change descriptions and topics, then re-run.

### Required PAT scopes

| Token type | Required permission |
|---|---|
| Fine-grained | `Repository metadata` → Read & Write (org-level) |
| Classic | `repo` (or `public_repo` for public repos only) |
