# Claude Desktop Bootstrap 2.0

A macOS launcher for an **already configured third-party Claude Desktop**.
Configuration belongs to `claude-config`: Bootstrap checks an explicit Machine,
applies the same reviewed plan, then asks macOS to open the bound application.

Bootstrap source and its Dock application builder live in **claudespace** as a
local utility. It is not a skill or plugin. App preferences live in an **App
Profile** in `claude-config-data`; local paths live in a **Machine** file.
Provider configuration, credentials and deployment mode remain with Desktop and
CC Switch.

## Requirements and boundaries

- macOS, an installed `claude-config` **0.1.4+**, and an explicit existing Machine.
- A working third-party Desktop setup in the native directory
  `~/Library/Application Support/Claude-3p`, with a saved applied configuration.
- Python **3.9+** is needed only to build or restore the Dock app. Clicking the
  built app uses macOS tools and the installed `claude-config` command.
- Run as your normal login user. The launcher does not create a third-party
  deployment, choose a provider, sign in, or modify the official deployment.

An arbitrary Machine `data_root` does not redirect Desktop. The launcher rejects
custom data roots before applying anything. The inspected signed Desktop build
ignores `CLAUDE_USER_DATA_DIR`; Bootstrap does not try to override that behavior.
A Machine pointing to the official `Claude` directory cannot use this launcher.

Desktop's deployment choice is read from `claude_desktop_config.json`, **not**
`config.json`. The latter contains ordinary preferences. `claude-config` reads
`configLibrary/_meta.json` to find the applied feature-preference file. It never
writes the deployment choice, provider configuration or applied-profile pointer.
These locations were checked in installed Desktop **2.26454.2**; the framework
also checks its audited preference interface. File checks do not establish that
a provider account or actual GUI session works.

## Profile and Machine

Example App Profile, saved as
`profiles/apps/claude-desktop/third-party.yaml` in the configuration data repo:

```yaml
schema_version: 1
app: claude-desktop
settings:
  chatTabEnabled: true
  autoModeEnabled: true
  builtinBrowserEnabled: true
```

All fields are optional. Omitted settings preserve native values. The Auto and
browser switches control feature availability; native consent and organization
policy still apply. Provider keys and Claude Code settings do not belong here.

The corresponding entry in an existing Machine file is:

```yaml
apps:
  claude-desktop:
    profile: profiles/apps/claude-desktop/third-party.yaml
    binding:
      application: /Applications/Claude.app
      data_root: /Users/your-name/Library/Application Support/Claude-3p
```

Use the actual account's absolute path. This is a Machine fragment, not a
complete Machine file. Prepare the target machine's existing third-party setup
and binding explicitly; changing this fragment does not switch Desktop's mode.

## Preview and launch

From this source directory, preview the exact target Machine:

```sh
./launch.command --machine /absolute/path/third-party-machine.yaml --dry-run
```

This runs `claude-config plan --app claude-desktop --format json`, saves the
framework's report and prints a short result with its path. It neither applies
configuration nor launches Desktop. If the command is not on PATH, add
`--claude-config /absolute/path/to/claude-config`; the default also checks
`~/.local/bin/claude-config`.

To apply and launch, omit `--dry-run`. The order is:

1. Obtain a valid saved `plan` report for the explicit Machine.
2. Verify the third-party native directory and report binding.
3. Run `apply --expect-plan-id <that-plan-id> --format json` for the same Machine.
4. Check successful execution (`completed` or `unchanged`) and identical binding.
5. Call `open -a` with the bound application's absolute path.

Configuration conflicts, stale plans, missing bindings or failed reports stop
launch. If a write requires Desktop to close, the error asks you to save work and
quit normally with **Cmd-Q**. Bootstrap never terminates it. A successful no-op
can open or activate the existing app.

Use the framework directly to review individual differences or resolve conflicts:

```sh
claude-config plan --app claude-desktop --machine /absolute/path/third-party-machine.yaml
```

The launcher adds no conflict policy, merge engine, configuration cache or native
backup system. The framework owns these operations and its normal recovery
journal. Failure retains the launch attempt's raw stdout/stderr in a private
`claude-bootstrap.*` temporary directory and prints that location; success
removes that temporary directory. Full framework reports stay in its state
folder, normally `<config_dir>/.state/reports/`.

## Download a fixed version

Download `claude-desktop-bootstrap-2.0.0.tar.gz` from the
[Bootstrap 2.0.0 Release](https://github.com/LKCY23/claudespace/releases/tag/bootstrap-v2.0.0),
then extract it on the target Mac:

```sh
tar -xzf claude-desktop-bootstrap-2.0.0.tar.gz
cd claude-desktop-bootstrap-2.0.0
```

The archive contains only this utility's source, builder, documentation and tests.
It contains no Machine, preferences, credentials, installed application or Python
runtime. Install the current stable `claude-config` separately (0.2.0 was used
for this release's integration tests), then prepare the explicit third-party
Machine. Preview with `launch.command --dry-run` before building or replacing
its launcher. Downloading the archive does not install or apply anything.

The Dock app is built on its destination Mac because it records that machine's
CLI and Machine paths. Do not copy a pre-bound `.app` from another machine.
Bootstrap releases use `bootstrap-v<version>`; they are separate from resource
`baseline-<SHA>` releases and are not adopted through `fetch-baseline`.

## Dock application

Build on the target machine:

```sh
python3 install-app.py --machine /absolute/path/third-party-machine.yaml
```

The default output is `~/Applications/Claude Bootstrap.app`. Drag it to the Dock.
Errors appear in a native dialog. The app bundles `launch.command` and its report
helper; it records absolute paths to the installed `claude-config` command and
Machine file. It does not depend on the source checkout or a recorded Python
interpreter when clicked. Changes to the selected Profile take effect on the
next run; the Machine still determines which Profile and application to use.

To update the app or its Machine/command paths:

```sh
python3 install-app.py --machine /absolute/path/third-party-machine.yaml --replace
```

Use `--claude-config` to pin a different installed executable and `--output` for
another destination. `--icon-from` selects an installed Claude app for artwork
only, not the launch target. The icon retains the Claude artwork and green play
badge. The app is ad-hoc signed for local use, not notarized for distribution.
Building does not apply preferences, open Desktop, alter its app bundle, or add
Dock items, login items or background services.

Replacement accepts only this utility's bundle ID, retains the previous app in
`.claude-bootstrap-backups/` beside the destination and restores it if publication
fails or is interrupted by Ctrl-C. Build failures leave the previous app in place.

Restore a retained **launcher app** without applying configuration:

```sh
python3 install-app.py --restore /absolute/path/to/retained.app --replace
```

The source backup remains, and the displaced current launcher is also retained.
A restored old launcher retains its old runtime dependencies; its availability
must be checked separately before use.

Restore **configuration** through the framework using the run ID in its report:

```sh
claude-config rollback --app claude-desktop --machine /absolute/path/third-party-machine.yaml --run RUN_ID
```

After reviewing that preview, repeat with `--write --expect-plan-id PLAN_ID`.
Launcher replacement and configuration rollback are separate operations.

## Upgrade from the old Bootstrap

The old `apply.py`, JSON overrides file and `--overrides` / `--data-dir` options
are removed. Move the selected preferences into an App Profile, install the
matching framework version, prepare the target Machine, preview it, then build
the new launcher. There is no fallback to old JSON merging.

Do not remove the old source checkout or overrides while an installed old app
still points at them. This refactor can be prepared in a separate worktree and
activated only when the target machine is ready. Official local deployment does
not need to change for source work or isolated tests.

## Tests

```sh
python3 -B -m unittest discover -s tests -v
zsh -n launch.command
```

Tests use temporary data, a synthetic CLI and uniquely identified synthetic apps.
They cover previews, failures, unchanged and changed application, quoted paths,
report binding, interrupted updates, restore, repeated Dock launches and signing.
They do not launch real Claude or apply a user's Machine file.

For the real-framework integration tests, install the framework's development
dependencies and set `CLAUDE_CONFIG_TEST_SOURCE=/absolute/framework/src` (or place
that source at `../framework/src`). Only native app probing and the application
itself are synthetic; field merging, plans, reports and recovery use framework
code. Without that source, those integration tests are explicitly skipped.
Native packaging tests require a macOS GUI session where `osacompile`, signing
and LaunchServices can operate.

This entry point orders its own launch only. Direct Claude launches can bypass
it; see [macOS automation notes](macos-automation.md). Network checks are outside
this implementation.

## Release verification boundary

The macOS CI checks preview/apply ordering, exact report identity, blocked and
unchanged cases, packaged scripts, signatures, replacement and recovery, and
integration with a pinned claude-config source. Synthetic apps and temporary
configuration are used throughout. Neither passing CI nor downloading this
release verifies a real third-party account, provider or Desktop GUI session.
Network-exit checks are not included. Official local deployments are unchanged.
