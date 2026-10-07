# Optional third-party research and browser tools

ARIS, agent-browser and AutoResearchClaw are registered in the root Claude
marketplace with fixed upstream commits. They are available on demand, not
selected by claude-config-data/agents.yaml and not installed by registration.
Their old manifest external-tool installation declarations were removed.

| Install ID | Fixed source | Separate setup |
| --- | --- | --- |
| aris@claudespace | wanshuiyin/Auto-claude-code-research-in-sleep at 26b95cfa0d8747078e9e43b42e20952709e561b8 | Review and run upstream setup only after choosing to use it |
| agent-browser@claudespace | vercel-labs/agent-browser at f7c8b071343dda29477a56cb336ea76144c05496, skills subtree | Matching agent-browser CLI 0.38.2 and explicit browser setup |
| autoresearchclaw@claudespace | Thin seven-skill adapter, based on aiming-lab/AutoResearchClaw at 2984bb62323eb1abfe481e4b950e3a4c4cdbefa6 | Python researchclaw runtime, project configuration and local provider credentials |

catalog.json records these same source-only entries for provenance. It is not
an installation selection file. The native marketplace manifest is the install
catalog. A source pin changes only after explicit review, never by following latest.

The AutoResearchClaw checkout had two local repair commits. The adapter keeps the
researchclaw skill YAML-frontmatter repair, with provenance and file hashes in
packages/autoresearchclaw/UPSTREAM.json. The Python runtime uses the publicly
retrievable upstream commit, not the local repair commit.

The local copied skills, source checkouts and two older agent-browser CLI versions
were retired on 2026-10-07. Their recovery material is private machine state, not
part of this repository. No personal configuration, research output or credentials
were copied into this catalog. Future installation uses the pinned upstream source;
it does not silently restore unversioned local variants.

## Install only when needed

After obtaining this catalog revision, use the normal native marketplace flow and
choose one install ID. For example:

```sh
claude plugin install aris@claudespace
claude plugin enable aris@claudespace
```

For agent-browser, choose the matching CLI release explicitly instead of latest:

```sh
npm install -g agent-browser@0.38.2
```

Browser downloads, authentication and source-specific setup are separate actions.
Read the selected plugin's documentation before doing them. These commands are
examples; registering or validating the marketplace does not execute them.

The declaration helper currently requires prepared local sources for managed
deployment. Before adding one of these remote references to agents.yaml, prepare
the pinned source or adapter and validate that plan. Until then, the source-only
entries are consumed by the native Claude marketplace installer. Codex adapters
are not installed or selected by this change.
