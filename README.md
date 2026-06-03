# claudespace

Personal [Claude Code](https://claude.ai/code) plugin marketplace — one catalog for all your self-authored and curated third-party skills, with exact version pinning via git.

## What problem does this solve?

Claude Code has two extension mechanisms — **skills** (flat file copies under `~/.claude/skills/`) and **plugins** (versioned, installed via `claude plugin install plugin@marketplace`). Managing skills as file copies means you lose track of where they came from, what version they're at, and whether there are upstream updates.

claudespace is a **marketplace**: a git repo with a `.claude-plugin/marketplace.json` catalog that tells Claude Code what plugins are available, where their code lives, and the exact commit to install. One `claude plugin marketplace add` gives you every skill in this catalog. Version bumps are explicit git operations — no silent drift.

## Quick Start

```bash
# 1. Register this marketplace (once per machine)
claude plugin marketplace add LKCY23/claudespace

# 2. Install any plugin
claude plugin install github@claudespace
claude plugin install deep-research@claudespace

# 3. Install everything
claude plugin install github@claudespace \
  research-brainstorm@claudespace \
  literature-review@claudespace \
  read-paper@claudespace \
  deep-research@claudespace \
  academic-paper@claudespace \
  academic-paper-reviewer@claudespace \
  academic-pipeline@claudespace \
  karpathy-llm-wiki@claudespace
```

If you use [claude-config](https://github.com/LKCY23/claude-config) for cross-machine config sync, you can reference these in `plugins.yaml` and let `claude-config apply` handle the installation.

## Plugin Catalog

| Plugin | Category | Source | Upstream |
|--------|----------|--------|----------|
| `github` | devtools | self-hosted | [claude-github-skill](https://github.com/LKCY23/claude-github-skill) |
| `research-brainstorm` | research | self-hosted | [research-brainstorm](https://github.com/LKCY23/research-brainstorm) |
| `literature-review` | research | self-hosted | [research-reading-skills](https://github.com/LKCY23/research-reading-skills) |
| `read-paper` | research | self-hosted | [research-reading-skills](https://github.com/LKCY23/research-reading-skills) |
| `deep-research` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-paper` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-paper-reviewer` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-pipeline` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `karpathy-llm-wiki` | knowledge | third-party | [karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) |

## Architecture: Two source modes

claudespace supports two plugin source patterns, both defined in `marketplace.json`:

### Mode 1 — Self-hosted (submodule)

The plugin code lives directly in this repository via git submodule. The version is determined by the submodule's pinned commit.

```
claudespace/
└── skills/
    └── github/              ← git submodule @ commit 8ba6659
        └── SKILL.md
```

```json
{ "name": "github", "source": "./skills/github" }
```

**Used for**: plugins you own — `github`, `research-brainstorm`, `literature-review`, `read-paper`.

### Mode 2 — External reference (pinned sha)

The plugin code lives in an external repository. The version is locked to an exact commit sha.

```json
{
  "name": "deep-research",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/Imbad0202/academic-research-skills",
    "path": "skills/deep-research",
    "ref": "main",
    "sha": "57507ef7a0b6828798d5de8f68a08b5943f43a87"
  }
}
```

**Used for**: third-party plugins you want to pin — `deep-research`, `academic-paper`, `academic-paper-reviewer`, `academic-pipeline`, `karpathy-llm-wiki`.

### Why two modes?

| | Mode 1 (self-hosted) | Mode 2 (external) |
|---|---|---|
| Version tracking | `git submodule status` | `sha` field in marketplace.json |
| Update mechanism | `git submodule update --remote` | manually update sha in marketplace.json |
| Git history | Full submodule history in this repo | No local copy of upstream code |
| Best for | Code you maintain and evolve | Curated third-party snapshots |

## Install

```bash
# Register marketplace
claude plugin marketplace add LKCY23/claudespace

# Install a specific plugin
claude plugin install <name>@claudespace

# List what's installed
claude plugin list
```

## Update

### Update self-hosted plugins (Mode 1)

```bash
cd claudespace
git submodule update --remote skills/github        # pull latest from upstream
git add skills/github                              # pin new commit
git commit -m "chore: update github to vX.Y.Z"
git push

# Then tell users to refresh their marketplace cache:
claude plugin marketplace update claudespace
claude plugin update github@claudespace
```

### Update third-party plugins (Mode 2)

```bash
# 1. Get the latest commit sha from upstream
gh api repos/Imbad0202/academic-research-skills/commits/HEAD --jq '.sha'

# 2. Edit marketplace.json: update the "sha" field for the plugin

# 3. Review the diff between old and new sha to verify nothing is broken

# 4. Commit and push
git add .claude-plugin/marketplace.json
git commit -m "chore: update deep-research to <new-sha>"
git push

# 5. Users refresh:
claude plugin marketplace update claudespace
claude plugin update deep-research@claudespace
```

## Add a new plugin

### Add your own (Mode 1)

```bash
# 1. Add as git submodule
git submodule add https://github.com/<you>/<repo>.git skills/<name>

# 2. Add entry to marketplace.json
# {
#   "name": "<name>",
#   "source": "./skills/<name>",
#   "description": "...",
#   "category": "..."
# }

# 3. Commit
git add .gitmodules skills/<name> .claude-plugin/marketplace.json
git commit -m "feat: add <name> plugin"
git push
```

### Curate a third-party (Mode 2)

```bash
# 1. Find the repo structure — locate the SKILL.md and note the subdirectory path

# 2. Get the latest commit sha
gh api repos/<owner>/<repo>/commits/HEAD --jq '.sha'

# 3. Add entry to marketplace.json
# {
#   "name": "<name>",
#   "source": {
#     "source": "git-subdir",
#     "url": "https://github.com/<owner>/<repo>",
#     "path": "<subdir>",
#     "ref": "main",
#     "sha": "<commit-sha>"
#   },
#   "description": "...",
#   "category": "...",
#   "author": { "name": "<owner>" }
# }

# 4. Commit
git add .claude-plugin/marketplace.json
git commit -m "feat: add <name> (third-party, pinned to <short-sha>)"
git push
```

## Repository Structure

```
claudespace/
├── .claude-plugin/
│   └── marketplace.json          ← Plugin catalog (the core of this repo)
├── .gitmodules                   ← Submodule definitions (self-hosted plugins)
├── skills/                       ← Self-hosted skill submodules
│   ├── github/                   ← git submodule → claude-github-skill
│   ├── research-brainstorm/      ← git submodule → research-brainstorm
│   └── research-reading-skills/  ← git submodule → research-reading-skills
│       └── skills/
│           ├── literature-review/
│           └── read-paper/
├── .gitignore
└── README.md
```

Third-party plugins (Mode 2) have no local files in this repo — they are referenced by URL and sha in `marketplace.json` and fetched on demand by `claude plugin install`.

## Relationship with claude-config

[claude-config](https://github.com/LKCY23/claude-config) is a cross-machine configuration sync tool. claudespace is the **skill source** — it defines what skills exist and at what versions. claude-config is the **deployment tool** — it applies configurations (including plugin installations) to any machine.

```
claudespace                     claude-config
  │                               │
  │ marketplace.json  ──ref──→    │ plugins.yaml
  │ (what & which version)        │ (what to install where)
  │                               │
  │  claude plugin install        │  claude-config apply
  │  github@claudespace           │  → calls plugin install
  │                               │
```

If you use both, reference claudespace plugins in claude-config's `plugins.yaml` and run `claude-config apply` — it will handle marketplace registration and plugin installation for you.

## Version Policy

- **All plugins are pinned to exact commits** — no automatic tracking of `main`/`latest`
- **Updates are manual and reviewed** — before bumping a sha, review the upstream diff to avoid breaking changes
- **Self-hosted plugins** are pinned via submodule commit; `git submodule update --remote` fetches latest but does not auto-commit
- **Third-party plugins** are pinned via `sha` in marketplace.json; update requires an explicit edit and commit

This is intentional: a marketplace is a **curated catalog**, not a firehose. You decide when to upgrade.

## License

This repository contains both original work and third-party plugin references. Each self-hosted submodule carries its own license. Third-party plugins referenced in `marketplace.json` remain under their respective upstream licenses.
