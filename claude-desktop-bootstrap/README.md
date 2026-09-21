# Claude Desktop bootstrap

A self-contained **local host configuration utility**, not a Claude Code skill or
plugin. It merges explicitly selected Claude Desktop deployment-policy values
into the applied local profile, and optionally opens Desktop afterwards.

## Code, personal configuration, and runtime state

- **claudespace** contains this tool, tests, documentation, and
  [overrides.example.json](overrides.example.json). The example is never loaded
  automatically.
- **Your configuration data repository** contains the actual non-sensitive
  preferences. In this setup, the file is
  `~/claude-config-data/assets/settings/claude-desktop-mac.json`.
- **Desktop's user-data directory** retains the full runtime profile, credentials,
  and private backups. Do not commit those files to either repository.

Every normal invocation requires `--overrides FILE`. There is no implicit lookup
in this checkout or fallback to the example. Restore is the only operation that
does not require an overrides file. The tool does not execute `claude-config
apply` or parse that framework's manifest; its Desktop archive pointer is separate
from the Claude Code settings merge inputs.

The example demonstrates three supported boolean fields:

```json
{
  "chatTabEnabled": true,
  "autoModeEnabled": true,
  "builtinBrowserEnabled": true
}
```

`autoModeEnabled` makes Auto mode **available**; it does not select a session mode,
grant consent, enable bypass permissions, or override organization policy.
`builtinBrowserEnabled` permits the built-in browser subject to Desktop's other
user and policy controls. No Claude Code permissions or consent records are edited.

## Requirements

- macOS, Python **3.9+**, and an existing Claude Desktop **third-party (`3p`)**
  deployment with a saved, applied profile.
- Python standard library and built-in macOS tools only; no package installation
  or network access is performed.
- Profile loading and the original Chat/Auto keys were inspected in Desktop
  **2.2553.1**; the built-in browser flag was also confirmed in the local profile.
  This local format is not a promised stable API; recheck after Desktop updates.
- Run as the normal login user, not `sudo`.

## Quick start

These examples use the actual configuration-data checkout above; substitute your
own file path if necessary. The JSON must already exist. For a new setup, copy
`overrides.example.json` outside this code repository and review the values first.

### Preview

From the claudespace repository root:

```bash
python3 claude-desktop-bootstrap/apply.py --overrides "$HOME/claude-config-data/assets/settings/claude-desktop-mac.json" --dry-run
```

Omitting a mode flag also previews. Output includes the target and changed field
names, never configuration values; a dry run writes nothing.

### Dock application

Build a normal macOS application with the external configuration path:

```bash
python3 claude-desktop-bootstrap/install-app.py --overrides "$HOME/claude-config-data/assets/settings/claude-desktop-mac.json"
```

This creates `~/Applications/Claude Bootstrap.app`. Drag it to the application
side of the Dock. Clicking it applies the chosen overrides and opens Claude,
without Terminal; errors appear in a native dialog. It uses a parameterless
AppleScript `run` handler, not a command-line argument handler. The app and Claude
are separate apps, so Claude retains its own running Dock icon.

The app records absolute paths to Python, this checkout's `apply.py`, and the
external overrides file. **It records a path, not a copy of your preferences.**
Edits to the data file take effect on the next launcher run. The installer checks
that the file exists and is a regular user-owned file; the bootstrap validates its
JSON and values on every run. Missing configuration is an error, not permission
to use example values.

To update an existing app, including apps built before external configuration was
required, or to change any recorded path:

```bash
python3 claude-desktop-bootstrap/install-app.py --replace --overrides "$HOME/claude-config-data/assets/settings/claude-desktop-mac.json"
```

Keep the two checkouts and Python installed. Replacement only accepts this
utility's bundle identifier, retains the old app under
`~/Applications/.claude-bootstrap-backups/`, and restores it if publication fails.
`--output "/absolute/path/Claude Bootstrap.app"` selects another install location.

The icon uses the installed **Claude artwork with a green play badge**. macOS's
icon service supplies the base; full-bleed artwork avoids an extra background
plate on macOS 27. `--icon-from "/path/to/Claude.app"` chooses the artwork source,
not the launch target. Older macOS versions may render the enclosure differently.
The app is ad-hoc signed for local use, not notarized for distribution. Building
it requires no Xcode and does not apply settings, launch Claude, change the Dock,
install a login item, or modify the original Claude.app.

### Command-line launch or standalone apply

If a write is needed, **quit Desktop with Cmd-Q first** and use an external
Terminal, not a session hosted inside the app being closed.

```bash
"$HOME/claudespace/claude-desktop-bootstrap/launch.command" --overrides "$HOME/claude-config-data/assets/settings/claude-desktop-mac.json"
```

```bash
python3 claude-desktop-bootstrap/apply.py --overrides "$HOME/claude-config-data/assets/settings/claude-desktop-mac.json" --apply
```

The launcher waits for a successful merge before calling macOS `open`. It never
quits or restarts an existing instance. If the stored profile already matches,
there is no write, and it can open/activate the running app.

`launch.command` forwards its arguments to `apply.py --launch`. It uses
`CLAUDE_BOOTSTRAP_PYTHON` when supplied, otherwise `PATH` and common Homebrew/Conda
locations before Apple's Python. The Dock app uses the interpreter recorded at
installation and does not depend on Finder's `PATH`.

Use `--data-dir` to choose a different Desktop **user-data root**, not a profile
file or `configLibrary`. The default is `~/Library/Application Support/Claude-3p`;
this option does not redirect Desktop itself or infer another deployment mode.
Use `--app "/path/to/Claude.app"` with `apply.py --launch` for another app location;
the bundle identifier must remain `com.anthropic.claudefordesktop`.

## Extending the external configuration

Edit your data repository's JSON, not the example, to add **verified flat Desktop
policy keys**. Only listed keys are replaced; unrelated fields are preserved.
Objects and arrays are whole-field replacements, not deep merges.

Validation rejects malformed JSON, duplicate keys, non-finite numbers, wrong
boolean types for the three example fields, and changed types for other existing
non-null fields. It is not Desktop's full schema: new keys, enums, array contents,
and version support require separate verification. Do not add Claude Code
`permissions`, `hooks`, or preference objects here.

Removing a key stops managing it; it does not remove the stored value. To disable
a boolean, explicitly set it to `false` and apply. Full rollback uses a backup.
Never put credentials in the example or commit complete profiles to the data repo.

## Files and write safety

Under the selected Desktop user-data root:

```text
Claude-3p/
├── configLibrary/
│   ├── _meta.json                 # Read only; appliedId selects the profile
│   └── <appliedId>.json           # Merge target; UUID is not hard-coded
├── bootstrap-backups/
│   └── <appliedId>/<timestamp>-<random>.json
└── .claude-desktop-bootstrap.lock # Advisory lock; intentionally retained
```

A real change resolves and validates the existing profile, refuses a running
Desktop or managed-policy conflict, locks other instances of this utility, and
backs up the original bytes. It then writes and flushes a same-directory temporary
file, rechecks the input snapshots and app state, and atomically replaces the
profile. Missing or malformed inputs are never replaced with empty configuration.

Published profiles and backups use mode `0600`; backup directories use `0700`.
Inputs must be user-owned regular files, not symbolic or hard links. The
`configLibrary` directory cannot be a symlink; the selected data root is resolved
before checks. A no-op creates no backup/lock and does not rewrite the profile.
Rejected writes may leave an empty lock or a valid backup. Handled failures clean
up temporary files; a force-kill may leave a private temporary file, not a
partially published profile.

Full-profile backups can contain credentials. They stay outside both repositories,
are never printed or uploaded, and are not automatically pruned. Do not attach
them to bug reports.

Desktop and other editors do not honor this advisory lock. A detected input
change aborts instead of retrying, but a window remains after the final check:
a competing writer can be overwritten or an app can read the older configuration.
Do not edit or independently launch Desktop during an apply.

The utility refuses local overrides if either managed-policy plist exists:

- `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist`
- `/Library/Managed Preferences/<login-user>/com.anthropic.claudefordesktop.plist`

It never edits or bypasses these policies. Separate Claude Code managed policies
can also restrict Auto mode regardless of the Desktop feature flag.

## Restore

Preview the backup path printed during an apply:

```bash
python3 claude-desktop-bootstrap/apply.py --restore "/absolute/path/to/printed-backup.json"
```

After reviewing and quitting Desktop:

```bash
python3 claude-desktop-bootstrap/apply.py --restore "/absolute/path/to/printed-backup.json" --apply
```

Restore only accepts the currently applied profile's own backup directory. It
restores the **entire profile**, including credentials and later changes, and backs
up the current state first. It does not change `appliedId` or `_meta.json`, and
needs no overrides file. A later launcher run reapplies the external preferences,
so update that file or stop using the launcher if the rollback should persist.
Deleting the utility alone does not undo already saved Desktop values.

## Automation and tests

The saved profile already persists across normal launches. The ordered launcher
is useful to reassert your preferences; it is not a global pre-launch interceptor.
See [macOS automation options](macos-automation.md) for native events and timing
limits. No resident helper, LaunchAgent, or login item is installed.

```bash
python3 -B -m unittest discover -s claude-desktop-bootstrap/tests -v
```

```bash
zsh -n claude-desktop-bootstrap/launch.command
```

Tests use synthetic temporary data, including explicit external configuration,
missing-file refusal, browser boolean validation, merging, backups, restore,
permissions, failure cleanup, and races. Native tests compile/sign a temporary
app and launch it through LaunchServices with a synthetic script, verify quoted
paths and live configuration changes, and recheck the signature and resolved icon.
They do not apply a real profile or restart Claude. A dry run checks the stored
merge plan, not the running UI; UI adoption requires a later full quit and launch.
Exit codes: `0` success/preview/no-op, `1` refused or failed operation, `2` invalid
arguments.
