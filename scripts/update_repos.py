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
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as exc:
        print(f"ERROR: Invalid YAML in config file {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"ERROR: Failed to read config file {path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"ERROR: Config file must contain a top-level mapping: {path}", file=sys.stderr)
        sys.exit(1)
    return data


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
    desired_topics = sorted(config.get("topics", [])) if "topics" in config else None
    desired_homepage = config.get("homepage")

    current_description = repo.description or ""
    current_topics = sorted(repo.get_topics())
    current_homepage = repo.homepage or ""

    if desired_description is not None and current_description != desired_description:
        changes.append(f"  description: {current_description!r} → {desired_description!r}")

    if desired_topics is not None and current_topics != desired_topics:
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
        if desired_topics is not None:
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
    org_name = config.get("org")
    if not isinstance(org_name, str) or not org_name.strip():
        print("ERROR: Config key 'org' is required and must be a non-empty string.", file=sys.stderr)
        sys.exit(1)

    defaults = config.get("defaults", {})
    if not isinstance(defaults, dict):
        print("ERROR: Config key 'defaults' must be a mapping.", file=sys.stderr)
        sys.exit(1)

    repos_config = config.get("repos", [])
    if not isinstance(repos_config, list):
        print("ERROR: Config key 'repos' must be a list.", file=sys.stderr)
        sys.exit(1)

    repo_overrides: dict[str, dict] = {}
    for i, repo_entry in enumerate(repos_config):
        if not isinstance(repo_entry, dict):
            print(f"ERROR: Config key 'repos[{i}]' must be a mapping.", file=sys.stderr)
            sys.exit(1)
        repo_name = repo_entry.get("name")
        if not isinstance(repo_name, str) or not repo_name.strip():
            print(
                f"ERROR: Config key 'repos[{i}].name' is required and must be a non-empty string.",
                file=sys.stderr,
            )
            sys.exit(1)
        repo_overrides[repo_name] = repo_entry

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
        # Apply org-wide defaults to every repo; per-repo overrides win.
        repo_config = {**defaults, **repo_overrides.get(repo.name, {})}
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
