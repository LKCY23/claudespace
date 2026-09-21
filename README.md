# claudespace

Personal [Claude Code](https://claude.ai/code) plugin marketplace and local Claude utilities — one catalog for self-authored and curated third-party skills, with exact plugin version pinning via git, plus self-contained host tools.

## What problem does this solve?

Claude Code has two extension mechanisms — **skills** (flat file copies under `~/.claude/skills/`) and **plugins** (versioned, installed via `claude plugin install plugin@marketplace`). Managing skills as file copies means you lose track of where they came from, what version they're at, and whether there are upstream updates.

claudespace is a **marketplace**: a git repo with a `.claude-plugin/marketplace.json` catalog that tells Claude Code what plugins are available, where their code lives, and the exact commit to install. One `claude plugin marketplace add` gives you every skill in this catalog. Version bumps are explicit git operations — no silent drift.

## Quick Start

```bash
# 1. Register this marketplace (once per machine)
claude plugin marketplace add LKCY23/claudespace

# 2. Install any plugin
claude plugin install github@claudespace
claude plugin install teach@claudespace
claude plugin install deep-research@claudespace

# 3. Install all marketplace plugins
claude plugin install github@claudespace \
  skill-evaluator@claudespace \
  teach@claudespace \
  programming-practice@claudespace \
  research-brainstorm@claudespace \
  research-dev-orchestrator@claudespace \
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
| `skill-evaluator` | devtools | self-hosted | [skill-evaluator](https://github.com/LKCY23/skill-evaluator) |
| `research-brainstorm` | research | self-hosted | [research-brainstorm](https://github.com/LKCY23/research-brainstorm) |
| `research-dev-orchestrator` | research | self-hosted | [research-dev-orchestrator](https://github.com/LKCY23/research-dev-orchestrator) |
| `teach` | productivity | self-hosted | [teach-skill](https://github.com/LKCY23/teach-skill) |
| `programming-practice` | productivity | self-hosted | [programming-practice](https://github.com/LKCY23/programming-practice) |
| `literature-review` | research | self-hosted | [research-reading-skills](https://github.com/LKCY23/research-reading-skills) |
| `read-paper` | research | self-hosted | [research-reading-skills](https://github.com/LKCY23/research-reading-skills) |
| `deep-research` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-paper` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-paper-reviewer` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `academic-pipeline` | research | third-party | [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) |
| `karpathy-llm-wiki` | knowledge | third-party | [karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) |

## Local utilities

Local host tools live in ordinary tracked directories, separate from `skills/`
and the plugin catalog. They are not skills or plugins and cannot be installed
with `claude plugin install`.

| Utility | Purpose | Entry point |
|---------|---------|-------------|
| [claude-desktop-bootstrap](claude-desktop-bootstrap/README.md) | Safely persist local Claude Desktop profile overrides on macOS | Optional Dock app; `apply.py` (preview), `launch.command` (apply, then open) |

Preview the default Chat and Allow Auto mode overrides from the repository root:

```bash
python3 claude-desktop-bootstrap/apply.py --dry-run
```

The utility dynamically resolves the applied `3p` profile, preserves unrelated
settings, and supports private backups and rollback. Writes require Desktop to
be stopped; it never quits/restarts the app or installs a background service.
See its [README](claude-desktop-bootstrap/README.md) for application instructions
and [macOS automation research](claude-desktop-bootstrap/macos-automation.md) for
native event hooks and their timing limits.

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

**Used for**: plugins maintained as submodules; see the self-hosted entries in the catalog.

### Mode 2 — External reference (pinned sha)

The plugin code lives in an external repository. The version is locked to an exact commit sha.

```json
{
  "name": "deep-research",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/Imbad0202/academic-research-skills",
    "path": "deep-research",
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
├── claude-desktop-bootstrap/      ← Local host utility (not a plugin/submodule)
│   ├── apply.py                  ← Preview, merge, backup, and restore
│   ├── overrides.json            ← Declarative Desktop policy values
│   ├── launch.command            ← Apply successfully before opening Desktop
│   ├── install-app.py            ← Build a user-local, Dock-friendly macOS app
│   ├── app/                      ← App launcher and icon sources
│   ├── tests/                    ← Isolated configuration and native app tests
│   ├── macos-automation.md        ← Native launch-event research and limits
│   └── README.md
├── skills/                       ← Self-hosted skill submodules
│   ├── github/                   ← git submodule → claude-github-skill
│   ├── skill-evaluator/          ← git submodule → skill-evaluator
│   ├── research-brainstorm/      ← git submodule → research-brainstorm
│   ├── research-dev-orchestrator/ ← git submodule → research-dev-orchestrator
│   ├── teach/                    ← git submodule → teach-skill
│   ├── programming-practice/     ← git submodule → programming-practice
│   └── research-reading-skills/  ← git submodule → research-reading-skills
│       └── skills/
│           ├── literature-review/
│           └── read-paper/
├── .gitignore
└── README.md
```

Third-party plugins (Mode 2) have no local files in this repo — they are referenced by URL and sha in `marketplace.json` and fetched on demand by `claude plugin install`.

## Relationship with claude-config

[claude-config](https://github.com/LKCY23/claude-config) is a cross-machine configuration sync tool. For plugins, claudespace is the **skill source** — it defines what skills exist and at what versions. claude-config is the **deployment tool** — it applies configurations (including plugin installations) to any machine.

The separate local utilities are maintained here as source, not registered as
plugins. `claude-desktop-bootstrap` manages only a local Desktop profile; it does
not deploy Claude Code settings or participate in `claude-config apply`.

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

## Local development: skill-evaluator

`skills/skill-evaluator` is a self-authored plugin pinned by submodule commit,
with its own `.claude-plugin/plugin.json`. It is published at
[LKCY23/skill-evaluator](https://github.com/LKCY23/skill-evaluator), and its
submodule source is portable across machines.

The Codex discovery link `~/.codex/skills/skill-evaluator` points to this
submodule, so the active source is maintained here rather than as copied files.
Cross-machine deployment remains the responsibility of claude-config; the
submodule source is now hosted remotely.

## Local development: programming-practice

`skills/programming-practice` is a self-authored learning skill/plugin, version 0.1.1,
archived as a Git submodule pinned to an exact commit. It is published at
[LKCY23/programming-practice](https://github.com/LKCY23/programming-practice), so
other machines can initialize it from the canonical remote.

The learner owns practice code and commands; the tutor provides concept teaching,
graduated hints, debugging feedback, independent/transfer assessments, and optional
course-local records. It is separate from `teach` and does not replace that plugin.
See [the skill README](skills/programming-practice/README.md) for usage and
[validation scope](skills/programming-practice/tests/validation.md).

For a session-local trial, start Claude Code from the **learner project**:

```sh
CLAUDESPACE_ROOT="/path/to/claudespace"
claude --plugin-dir "$CLAUDESPACE_ROOT/skills/programming-practice"
```

Then invoke `/programming-practice:programming-practice`.

For **Codex**, expose that same directory through the learner project's
`.agents/skills/programming-practice` (or the user skill directory, not both).
`agents/openai.yaml` supplies Codex UI metadata; use the skill selector to select
it. The full package is discovered by the tested Codex CLI as
`programming-practice:programming-practice`, invoked with
`$programming-practice:programming-practice`. The Claude marketplace manifest is
not a Codex marketplace. See the skill README for the one-time local link setup.

Both hosts share the learner's `.programming-practice/` checkpoint, not chat
history. The installed skill has one teaching source; host configuration does
not create separate teachers. No global installation or claude-config deployment
is performed by this archive operation.

For cross-machine use, initialize the submodule from its GitHub URL and keep the
parent gitlink pinned; no local source path is advertised.
