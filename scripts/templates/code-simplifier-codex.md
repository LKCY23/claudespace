---
name: code-simplifier
description: Simplifies and refines recently modified code for clarity, consistency, and maintainability while preserving functionality. Main agent coordinates one independent simplifier subagent.
---

# Code Simplifier for Codex

This is the orchestration entry. The preserved upstream execution rules are at
`../../../agents/code-simplifier.md`, relative to this skill directory.

1. As the main agent, identify the requested files or recent diff, the behavior
   that must stay unchanged, applicable project instructions, and relevant
   verification. Keep the scope limited to the current request. For review-only
   requests, edits are not authorized.
2. Dispatch ONE independent subagent using the host's subagent facility. Give it
   the absolute upstream rule path, working directory, exact scope or diff,
   project/user constraints, review-only versus editing mode, and verification.
   Ask it to read the full upstream rule file and follow its execution rules.
   Claude-only `model: opus` metadata does not select a Codex model; inherit the
   current host's supported model configuration. User and project instructions
   take precedence over upstream stylistic preferences.
3. The subagent is the executor: it must not re-invoke this orchestration skill
   or dispatch another simplifier. In editing mode, it may refine only the
   assigned code and run relevant checks. In review-only mode, it reports
   concrete suggestions without edits. Ask for changes/findings, verification
   evidence, and remaining uncertainty. Having no useful changes is acceptable.
4. Wait for the subagent, inspect its findings or actual diff, check scope and
   behavior preservation, and integrate the result. Do not present discovery,
   dispatch or an unsupported assertion as a completed independent review.

If the host exposes no independent subagent facility, report that this invocation
cannot meet the independent-execution requirement. Do not silently do the work
in the main context or claim that a subagent ran.
