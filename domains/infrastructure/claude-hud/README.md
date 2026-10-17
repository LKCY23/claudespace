# Claude HUD installed baseline

This catalog preserves the currently enabled Claude HUD 0.0.10 package for
configuration migration. Plugin selection belongs to claude-config-data/agents.yaml.

The original installed package is under packages/claude-hud, with its author,
license, commands and built assets unchanged. catalog.json pins the exact package
fingerprint. Native process leases under .in_use are runtime metadata and excluded.

This is an installed-content snapshot, not a new upstream release or a claim that
the commit in the old installation receipt reproduces these bytes. Updates require
an explicit source and version review. Claude only; no Codex port is selected.

The framework may preserve an existing registration at another path only when the
selected package is already installed at this exact version and content hash. A
fresh host registers this catalog normally. Missing or changed installations block
preservation; existing registrations are never moved by that policy.
