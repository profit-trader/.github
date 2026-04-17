# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyGithub>=2.1.1",
#   "pyyaml>=6.0",
# ]
# ///
"""
update_repos.py — Org-wide repository metadata maintenance for profit-trader.

Usage:
    uv run scripts/update_repos.py
    uv run scripts/update_repos.py --dry-run     # preview changes without applying
    uv run scripts/update_repos.py --repo handbook  # target a single repo

Requirements:
    export GITHUB_TOKEN=<fine-grained PAT with org repo metadata read/write>
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from github import Auth, Github, GithubException

CONFIG_FILE = Path(__file__).parent / "repo_config.yaml"


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def github_error_message(exc: GithubException) -> str:
    data = exc.data
    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, str) and message:
            return message
        return repr(data)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    if isinstance(data, str) and data:
        return data
    status = getattr(exc, "status", None)
    return f"GitHub API error{f' (HTTP {status})' if status is not None else ''}"


def update_repo(repo, config: dict, dry_run: bool) -> list[str]:
    """Apply config to a single repo. Returns list of changes made (or that would be made)."""
    changes = []

    desired_description = config.get("description")
    desired_topics = sorted(config.get("topics", []))
    desired_homepage = config.get("homepage")

    current_description = repo.description or ""
    current_topics = sorted(repo.get_topics())
    current_homepage = repo.homepage or ""

    if desired_description is not None and current_description != desired_description:
        changes.append(f"  description: {current_description!r} → {desired_description!r}")

    if desired_topics and current_topics != desired_topics:
        changes.append(f"  topics:      {current_topics} → {desired_topics}")

    if desired_homepage is not None and current_homepage != desired_homepage:
        changes.append(f"  homepage:    {current_homepage!r} → {desired_homepage!r}")

    if changes and not dry_run:
        kwargs: dict = {}
        if desired_description is not None:
            kwargs["description"] = desired_description
        if desired_homepage is not None:
            kwargs["homepage"] = desired_homepage
        if kwargs:
            repo.edit(**kwargs)
        if desired_topics:
            repo.replace_topics(desired_topics)

    return changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update profit-trader org repository metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them.",
    )
    parser.add_argument(
        "--repo",
        metavar="NAME",
        help="Only update a single named repository.",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    config = load_config(CONFIG_FILE)
    org_name: str = config["org"]
    defaults: dict = config.get("defaults", {})
    repo_overrides: dict[str, dict] = {r["name"]: r for r in config.get("repos", [])}

    g = Github(auth=Auth.Token(token))
    try:
        org = g.get_organization(org_name)
    except GithubException as exc:
        print(
            f"ERROR: Failed to access organization '{org_name}': {github_error_message(exc)}",
            file=sys.stderr,
        )
        sys.exit(1)

    mode_prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode_prefix}Updating repos in '{org_name}'...\n")

    try:
        repos = [org.get_repo(args.repo)] if args.repo else list(org.get_repos())
    except GithubException as exc:
        target = f"repo '{args.repo}'" if args.repo else f"repos for org '{org_name}'"
        print(f"ERROR: Failed to load {target}: {github_error_message(exc)}", file=sys.stderr)
        sys.exit(1)

    total_changed = 0
    errors = 0
    for repo in repos:
        # Merge defaults with per-repo overrides (overrides win)
        repo_config = {**defaults, **repo_overrides.get(repo.name, {})}
        if not repo_config:
            print(f"  SKIP    {repo.name}  (no config entry)")
            continue
        try:
            changes = update_repo(repo, repo_config, dry_run=args.dry_run)
            if changes:
                total_changed += 1
                verb = "WOULD UPDATE" if args.dry_run else "UPDATED"
                print(f"  {verb}  {repo.name}")
                for c in changes:
                    print(c)
            else:
                print(f"  OK      {repo.name}")
        except GithubException as exc:
            errors += 1
            print(f"  ERROR   {repo.name}: {github_error_message(exc)}", file=sys.stderr)

    verb = "would be" if args.dry_run else "were"
    print(f"\n{mode_prefix}Done. {total_changed} repo(s) {verb} updated, {errors} error(s).")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
