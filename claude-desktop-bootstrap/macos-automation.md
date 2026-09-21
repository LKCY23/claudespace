# macOS startup automation

Research checked against Apple's documentation on **2026-09-21**. The local
machine reports Darwin 27. These are documented capabilities and timing limits,
not an end-to-end test of an installed automation or background service.

## Recommendation

Use the applied Desktop profile for persistence. When launch-time enforcement is
wanted, run the included [launch.command](launch.command): it waits for a
successful configuration merge before asking macOS to open Claude. The optional
[Claude Bootstrap app](README.md#app-icon) provides the same ordered launch from
a normal, Dock-friendly application icon; no Terminal or Shortcut is required.

For an alternative graphical entry point, create a **normal shortcut** in Shortcuts
with a **Run Shell Script** action, using this command (adjust the checkout path):

```bash
"$HOME/claudespace/claude-desktop-bootstrap/launch.command"
```

Use that shortcut instead of the original Claude icon, for example from the Dock
or a keyboard shortcut. If needed, supply an absolute Python executable with
`CLAUDE_BOOTSTRAP_PYTHON` as described in the [README](README.md#python-and-path-selection).
The user controls Shortcuts' permission to run scripts; this utility does not
change that security setting.

This is a **replacement launch entry point**, not an automation triggered by
Claude already being open. Direct launches through the original Dock item,
Finder, Spotlight, login items, app updates, or macOS reopen can bypass it. The
persisted values still remain on disk, but the override manifest is not
reapplied on those bypassed launches.

## What Apple provides

| Mechanism | Trigger | Can it guarantee our merge finishes before Claude reads its profile? |
|---|---|---|
| Wrapper / normal Shortcut | User invokes our entry point | Yes for that entry point, provided there is no competing launch |
| `NSWorkspace.willLaunchApplicationNotification` | Finder is about to launch an app | No documented completion barrier |
| `NSWorkspace.didLaunchApplicationNotification` | App has launched | No; startup reading may already have happened |
| Shortcuts App automation | An app opens | No; an open event is not a pre-initialization barrier |
| `NSWorkspace.didTerminateApplicationNotification` | App finishes executing | Prepares a later launch only; immediate relaunch can race |
| LaunchAgent `RunAtLoad` | The job is loaded/bootstrapped | No; not every Claude launch |
| LaunchAgent `KeepAlive` | Keeps that helper job running | No; not another application's launch trigger |

### NSWorkspace application notifications

Apple **does have a will-launch notification**. Its documented description is:

> A notification that the workspace posts when the Finder is about to launch an app.

However, the documentation does not say that Finder/Claude waits for an observer
or a spawned shell script to finish. An advance notification is not a synchronous
interceptor or an execution-order guarantee. The `didLaunch` notification is
later still. Neither is suitable for promising that startup-loaded configuration
will already be on disk.

For monitoring, a helper can subscribe through
`NSWorkspace.shared.notificationCenter` and filter the notification's
`NSRunningApplication` using the bundle identifier
`com.anthropic.claudefordesktop`. Apple documents exclusions for background and
`LSUIElement` applications; these notifications are not a universal process hook.

An exit notification can trigger a best-effort apply for the **next** launch.
Rapid quit-and-relaunch can beat that helper. Atomic replacement prevents a
half-written JSON file, but does not stop a new process from reading the old
file. This utility therefore refuses a needed write if Claude is already running
rather than silently claiming the change took effect.

### LaunchAgents

A user LaunchAgent can start/maintain such an observer at login. `RunAtLoad` means
run when that **job** is loaded, not every time some unrelated application opens.
`KeepAlive` maintains the helper's lifecycle; it creates no ordering dependency
with Claude's GUI startup. The exact `RunAtLoad` semantics were also checked in
the installed `launchd.plist(5)` manual.

`WatchPaths` watches filesystem changes, not application execution. The installed
manual warns that these events are race-prone; it is not a solution for enforcing
pre-launch ordering. Watching an app bundle does not mean observing its launches.

If event monitoring becomes necessary, the appropriate personal-tool mechanism
is an ordinary user helper in `~/Library/LaunchAgents`, with absolute
`ProgramArguments`, private logs, and no root access. A packaged/signed application
can use `SMAppService` to register a bundled LaunchAgent. Neither registration
mechanism changes the notification timing limitations.

No LaunchAgent, LaunchDaemon, login item, or resident helper is included or
installed here: the applied profile and ordered launcher solve the current
problem without a background process.

### Shortcuts on Mac

Apple's current **Mac-specific, macOS 27** guide explicitly lists opening an app
as an automation trigger. This is not an inference from the iPhone/iPad
"App — Is Opened" feature. Minimum macOS support was not established, so do not
assume older macOS releases offer the same UI. App-close automation on Mac was
not confirmed by this research.

An app-open automation cannot guarantee it runs before that app initializes.
Attaching `apply.py --apply` to Claude's app-open event would meet the script's
running-app guard and refuse a needed write. Automatically quitting/restarting
Claude from that event would risk interrupted work and restart loops. Use the
normal shortcut entry point above instead.

## Boundaries

- Claude Code `SessionStart` runs when a Code session starts, after Desktop has
  initialized. It is not a Desktop process pre-launch hook.
- Ordinary `defaults write` in the user preferences domain is not the verified
  input source for these two Desktop deployment-policy keys. Do not create managed
  preferences or override organizational restrictions to imitate persistence.
- Do not modify `Claude.app`, inject into its process, swizzle launch APIs, or use
  Accessibility to click configuration switches.
- No OS-wide interception of every launch is claimed. If another program can
  launch Claude independently, this utility cannot impose an ordering barrier on
  that program.

## Apple sources

- [NSWorkspace.willLaunchApplicationNotification](https://developer.apple.com/documentation/appkit/nsworkspace/willlaunchapplicationnotification)
- [NSWorkspace.didLaunchApplicationNotification](https://developer.apple.com/documentation/appkit/nsworkspace/didlaunchapplicationnotification)
- [NSWorkspace.didTerminateApplicationNotification](https://developer.apple.com/documentation/appkit/nsworkspace/didterminateapplicationnotification)
- [Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice)
- [Intro to shortcuts with automations in Shortcuts on Mac](https://support.apple.com/guide/shortcuts-mac/intro-to-automation-shortcuts-apd690170742/mac)
- [Add automations to Shortcuts on Mac](https://support.apple.com/guide/shortcuts-mac/add-automations-apdfbdbd7123/mac)
- [Shortcuts User Guide for Mac](https://support.apple.com/guide/shortcuts-mac/welcome/mac)
