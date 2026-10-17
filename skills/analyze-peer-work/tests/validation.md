# Validation — 2026-10-16

Target: analyze-peer-work 0.1.0. The tested instruction and metadata hashes are in [host-discovery.json](host-discovery.json).

## Executed checks

- Skill Creator `quick_validate.py`: frontmatter and scaffold checks passed.
- Claude Code 2.1.278 `plugin validate --json --strict`: passed without manifest warnings or errors.
- Claude Code session-local `--plugin-dir ... plugin details analyze-peer-work`: loaded version 0.1.0 with exactly one skill and no agents, hooks, MCP servers, or LSP servers. This was not a persistent Claude installation.
- Codex CLI 0.160.0 `app-server` initialization and `skills/list`: first verified discovery through a temporary project link; after correcting the metadata prompt to the observed namespaced invocation, verified the final package through its single user-level link. The final result was enabled, scope `user`, name `analyze-peer-work:analyze-peer-work`, with the expected display name and prompt and no reported discovery errors.
- JSON/YAML consistency, source registration, local Markdown links, evidence hashes, and whitespace checks passed. The root marketplace contains one entry pointing to this source.
- The installed claude-config helper's `validate --agent codex` passed for the existing selected plan. Its preview also reported a pre-existing model/reasoning preference difference (`changed: true`); no apply was run and those settings were not changed. This check is not evidence that the new skill was deployed by claude-config.

No model request or persistent trust change was made by the host checks. A local discovery link was intentionally created at the user skills entry; no installed plugin cache was edited. Source registration and local development availability are separate from profile selection, published baselines, and managed cross-machine deployment.

## Author review

Reviewed [the behavior cases](scenarios.md) against the instructions for requirement focus, evidence levels, taxonomy, conditional adoption advice, continuation from existing notes, output flexibility, and feedback from actual validation. Mandatory rules govern analytical claims; recommended steps and output forms can be adapted. No fixed headings, approval stages, scoring matrix, figure quota, file bundle, or subagent requirement is imposed.

This is author review, not an independent model run. The cases remain proposed behavior evaluations.

## Not established by these checks

- Reliable automatic activation or actual model adherence on the scenario cases.
- Improved analysis quality compared with a baseline without the skill.
- Desktop UI refresh behavior, other host versions, or other machines.
- A remote release, a pinned consumer baseline, or persistent Claude plugin installation.

Discovery proves that the host can load the package; it does not prove the quality of an analysis produced with it.
