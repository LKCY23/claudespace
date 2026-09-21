# Claude Desktop bootstrap

A self-contained **local host configuration utility**, not a Claude Code skill or
plugin. It keeps selected Claude Desktop deployment-policy values in the applied
local profile. It is tracked directly in claudespace, not installed through the
plugin marketplace or copied into `~/.claude/skills/`.

## Scope and prerequisites

- macOS, Python **3.9+**, and an existing Claude Desktop **third-party (`3p`)
  deployment** with a saved, applied profile.
- Standard library only: no `pip install`, API calls, or network access.
- The profile-loading behavior and the two default keys were inspected in
  **Claude Desktop 2.2553.1 on 2026-09-21**. This is a local configuration format,
  not a promised stable public API; recheck compatibility after Desktop updates.
- Use your normal login user, not `sudo`.

The supplied [overrides.json](overrides.json) contains:

```json
{
  "chatTabEnabled": true,
  "autoModeEnabled": true
}
```

`autoModeEnabled` makes Auto mode **available**. It does not select Auto mode for
sessions, grant consent, enable bypass permissions, or override organization
policy. This utility does not modify Claude Code settings, hooks, or permission
acknowledgements.

## Quick start

### App icon

Build a normal macOS application in your user Applications folder:

```bash
python3 claude-desktop-bootstrap/install-app.py
```

This creates `~/Applications/Claude Bootstrap.app`, using the **original installed
Claude app icon with a green play badge** in the lower-right corner. The base icon
is read through macOS's icon service, including the app's asset-catalog artwork;
the Claude logo is not redrawn. The renderer removes the system icon's outer
transparent margin and supplies full-bleed artwork for macOS to mask, avoiding a
second gray background plate. The displayed result is tested on macOS 27; older
macOS versions may render the enclosure differently. Drag it from Finder to the
application side of the Dock. The default icon source is `/Applications/Claude.app`;
use `--icon-from "/absolute/path/to/Claude.app"` if it lives elsewhere. This flag
only selects the artwork source, not the app launch target.
Clicking it runs the same guarded `apply.py --launch` operation without opening
Terminal. The app uses a parameterless AppleScript `run` handler and does not
parse command-line flags. For a read-only preview, run `apply.py --dry-run`
directly, not the app or its compiled AppleScript.
Errors appear in a native dialog; success opens Claude and the small
launcher exits. The launcher and Claude are separate apps, so Claude still has
its own running Dock icon.

The installer does **not** apply configuration, launch Claude, change Dock
preferences, register a login item, or modify the original `Claude.app`. It uses
macOS's built-in AppleScript compiler and image/signing tools, not Xcode. The app
is ad-hoc signed for local use, not a notarized distribution package.

The app records the absolute paths of this checkout's `apply.py` and the Python
interpreter used to run the installer. **Keep the checkout and Python installed.**
Edits to `overrides.json` and `apply.py` take effect on the next launcher run;
there is no copied configuration to keep in sync. If either path moves, rebuild:

```bash
python3 claude-desktop-bootstrap/install-app.py --replace
```

Replacement only accepts this utility's bundle identifier. A previous app is
retained under `~/Applications/.claude-bootstrap-backups/`; a failed publication
restores it. Use `--output "/absolute/path/Claude Bootstrap.app"` for a different
location. Deleting the launcher or removing it from the Dock does not undo saved
Desktop settings.

If Claude is already running and a configuration change is needed, the app
explains that you must save your work and quit Claude with Cmd-Q first. It does
not close the app or interrupt existing sessions for you.

### Command line

From the claudespace repository root, preview the changes:

```bash
python3 claude-desktop-bootstrap/apply.py --dry-run
```

Running without a mode flag is also a dry run. It prints the target path and
changed **field names**, never configuration values, and writes nothing.

To apply and launch, first **quit Claude Desktop with Cmd-Q**, then run this in
an **external Terminal**; the Desktop-hosted terminal/session may close with the
app:

```bash
"$HOME/claudespace/claude-desktop-bootstrap/launch.command"
```

Adjust the checkout path if it lives elsewhere. The launcher synchronously
applies the overrides, checks success, then uses macOS `open` to launch Claude.
It refuses a needed write while Claude is running. If the stored profile already
matches, it can open/activate Claude without a write; it never restarts an
already-running instance.

To apply without opening the app:

```bash
python3 claude-desktop-bootstrap/apply.py --apply
```

No launch service, login item, global shell configuration, or system setting is
installed by these commands.

### Python and path selection

`launch.command` uses `CLAUDE_BOOTSTRAP_PYTHON` when explicitly supplied. Otherwise
it looks for `python3` on `PATH`, with common Homebrew/Conda locations as fallbacks
before Apple's `/usr/bin/python3`. Finder and automation environments may not
inherit your interactive shell's `PATH`. Install Python yourself if necessary;
this tool does not install dependencies.

```bash
CLAUDE_BOOTSTRAP_PYTHON="/absolute/path/to/python3" "$HOME/claudespace/claude-desktop-bootstrap/launch.command"
```

For a non-default data location, use the **user-data root**, not `configLibrary`
or an individual profile file:

```bash
python3 claude-desktop-bootstrap/apply.py --data-dir "/absolute/path/to/Claude-3p" --dry-run
```

`--data-dir` chooses what the tool edits; it does **not** redirect Desktop itself
to that directory. It defaults to `~/Library/Application Support/Claude-3p`, not
the consumer `Claude` directory. The tool does not infer other deployment modes
or use `CLAUDE_USER_DATA_DIR` as an implicit override.

Use `--app "/absolute/path/to/Claude.app"` with `--launch` if the app is installed
elsewhere. The bundle identifier must be `com.anthropic.claudefordesktop`.
All launcher arguments are forwarded to `apply.py`; use `apply.py` directly for
dry-run, standalone apply, or restore rather than adding a second mode flag.

## Add more settings

Edit `overrides.json` to add **verified flat Desktop deployment-policy keys**.
Only keys explicitly present in that file are replaced. Unrelated profile fields
remain intact. Objects and arrays are whole-field replacements, **not deep
merges**.

Validation includes strict JSON, duplicate-key rejection, boolean checks for the
two default keys, and type consistency for other existing non-null fields. It is
**not Desktop's full schema**: new keys, enums, array contents, and version support
cannot be verified automatically. A typo or unsupported key can be ignored or
rejected by Desktop. Verify the installed app's schema before adding one, then
preview the result. Do not put Claude Code `permissions`, `hooks`, or preference
objects in this file.

Removing a key from the override file stops managing it; it **does not delete**
the stored value. To disable a boolean, explicitly set it to `false` and apply.
Use an appropriate backup for a full rollback.

For machine-specific or sensitive overrides, keep a separate JSON file outside
the repository:

```bash
python3 claude-desktop-bootstrap/apply.py --overrides "$HOME/.config/claude-desktop-bootstrap/overrides.json" --dry-run
```

The directory/file in this example must already exist. Never commit a copied
Desktop profile, gateway key, or other credential to this repository.

## Files read and written

Under the selected Desktop user-data root:

```text
Claude-3p/
├── configLibrary/
│   ├── _meta.json                 # Read only; appliedId selects the profile
│   └── <appliedId>.json           # Merge target; UUID is never hard-coded
├── bootstrap-backups/
│   └── <appliedId>/
│       └── <timestamp>-<random>.json
└── .claude-desktop-bootstrap.lock # Advisory lock; intentionally retained
```

For a real change, the tool:

1. Resolves the applied profile and rejects missing/malformed input rather than
   creating an empty replacement.
2. Refuses managed-policy conflicts or a running Desktop process. The running-app
   query uses AppKit by bundle identifier; it does not launch or activate Claude.
3. Locks out other instances of this utility and verifies the input snapshots.
4. Saves the original profile bytes to a private backup.
5. Writes and flushes a same-directory temporary file, rechecks the inputs and
   application state, then atomically replaces the profile.

Published profiles and backups use mode `0600`; backup directories use `0700`.
Inputs and configuration directories must be user-owned; symlinked profile
files/configLibrary directories and hard-linked input files are rejected.
The explicitly selected data root is resolved before these checks.

A no-op does not rewrite the profile or create a backup/lock. A rejected write
may leave an empty lock file; a late failure can leave a valid backup. Temporary
files are cleaned up on handled errors. A force-killed process can leave a private
temporary file, but it cannot publish a partially written profile.

### Credentials and concurrency

The utility necessarily **reads the whole profile** to preserve unrelated
settings. Full backups can contain gateway credentials. They stay in the local
Desktop data directory, outside the checkout, and are never printed or uploaded.
Backups are not automatically pruned; inspect and manage their retention locally.
Do not attach them to bug reports.

Desktop does not honor this tool's advisory lock. The checks reduce accidental
concurrent writes but are not a global launch barrier: do not open Claude or edit
its profile through another tool during an apply. A change detected by the
pre-commit checks causes an abort, not an automatic overwrite/retry. There is
still a window after the final check: a competing writer can be overwritten, or
a competing app launch can load the older configuration. Avoid those competing
operations; the tool cannot impose a lock on Desktop or other editors.

The tool conservatively stops if either Desktop managed-policy plist exists:

- `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist`
- `/Library/Managed Preferences/<login-user>/com.anthropic.claudefordesktop.plist`

It neither edits nor bypasses those files. Separate Claude Code managed policies
can also restrict Auto mode, regardless of the local Desktop feature flag.

## Backups and rollback

Use the backup path printed by a successful apply (replace the example path):

```bash
python3 claude-desktop-bootstrap/apply.py --restore "/absolute/path/to/printed-backup.json"
```

After reviewing the preview and quitting Desktop:

```bash
python3 claude-desktop-bootstrap/apply.py --restore "/absolute/path/to/printed-backup.json" --apply
```

Restore only accepts a backup in the **currently applied profile's own backup
directory**. It restores the **entire profile**, including credentials and all
changes made since that backup, and backs up the current state first. It does
not switch `appliedId` or restore `_meta.json`.

`--restore` ignores the override file. A subsequent normal launcher run applies
`overrides.json` again, so change that file or stop using the launcher if the
rollback is meant to remain in effect. Removing this utility alone does not undo
values already saved in Desktop.

## Startup automation on macOS

Once applied, the profile itself persists across normal launches; a startup hook
is not needed just to retain these two values. If you want to reassert the
manifest before each launch, use the [app icon](#app-icon) or `launch.command`
as your entry point. A normal macOS Shortcut can also run the command.

See [macOS automation options](macos-automation.md) for Apple's app events,
Shortcuts, LaunchAgents, timing limits, and official sources. No global per-app
pre-launch hook or background watcher is installed by this utility.

## Tests and verification limits

```bash
python3 -B -m unittest discover -s claude-desktop-bootstrap/tests -v
```

```bash
zsh -n claude-desktop-bootstrap/launch.command
```

Tests use synthetic profiles in temporary directories. They cover merging,
idempotency, validation, redacted output, backups, restore, permissions, races,
lock contention, failure cleanup, and launch ordering. On macOS, packaging tests
also compile/sign an app, generate its icon, and execute its compiled AppleScript
against a **synthetic Python script**, including paths with quotes and spaces.
GUI regressions launch a uniquely identified temporary app through LaunchServices
(`open -g -W`), the Finder/Dock launch mechanism, and verify the recorded
`--launch` invocation and signature after repeated launches. This is separate
from invoking a compiled script with `osascript`.
The real Claude app-open call is mocked; tests never restart Claude or apply
changes to a real profile. The default read-only preview is suitable for checking
the current machine separately.

A passing dry run confirms the target/merge plan, not that the running Desktop UI
has adopted those values. Actual UI verification requires a later full quit and
launch. Exit status is `0` for success/dry-run/no-op, `1` for a refused or failed
operation, and `2` for invalid command-line arguments.
