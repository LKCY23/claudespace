# claude-github-skill

A Claude Code skill for GitHub workflows that combines local `git` operations with remote GitHub actions through `gh`.

`SKILL.md` is the canonical skill definition in this repository. This README is the project landing page.

## What it does

The skill is designed for the full repository workflow, including:

- local repository state inspection
- branch management and sync flow
- commits, pulls, pushes, merges, and rebases
- pull request and issue workflows
- CI / workflow run inspection
- moving cleanly between local git state and remote GitHub collaboration

## Why this repo exists

This repository exists to develop, refine, and package the `/github` skill as a standalone project.

While the repository is used as the source workspace, the active installed copy can also live in Claude Code's global skills directory:

- `/Users/liyao/.claude/skills/github/SKILL.md`

That means you can keep iterating here while consuming the installed skill globally from Claude Code.

## Canonical source

- `SKILL.md` — canonical skill definition for this project
- `README.md` — project overview and usage notes
- `openclaw-github-SKILL.md` — upstream reference material used for comparison and adaptation

If README and `SKILL.md` ever diverge, treat `SKILL.md` as the source of truth.

## Install and use

### Option 1: global Claude Code install

Install or copy the skill into Claude Code's global skills directory so `/github` is available across repos:

```text
~/.claude/skills/github/SKILL.md
```

In this setup, this repository remains the authoring source while Claude Code consumes the globally installed skill.

### Option 2: consume from claudespace

This project can also be consumed from a larger skills workspace such as `claudespace`, where it may be included as a child repository or submodule for centralized skill management.

This README does not assume a specific parent-workspace setup. The child repo remains independently useful as the maintained source for the skill.

## Scope

The skill intentionally covers both sides of GitHub-centric development:

### Local Git workflow

- inspect repository state safely
- manage branches
- commit and sync changes
- merge or rebase with explicit user intent

### Remote GitHub workflow

- inspect or manage pull requests
- inspect or manage issues
- inspect CI and workflow runs
- bridge local branch state with GitHub collaboration flow

## Project goals

- keep Git and GitHub operations in one coherent skill
- prefer safe defaults for higher-impact actions
- make common workflows easy without hiding important repository state
- provide a reusable skill that works well as a global install or as part of a shared skills workspace

## Repository layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Canonical skill definition |
| `README.md` | Public project overview |
| `openclaw-github-SKILL.md` | Reference material |
| `.claude/settings.local.json` | Local Claude Code configuration for working in this repo |

## Status

The repository is the maintained source for the skill. Depending on your setup, Claude Code may consume it through a global install or via a parent workspace such as `claudespace`.

## License

No license file is currently included in this repository.
