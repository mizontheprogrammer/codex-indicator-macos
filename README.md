<p align="center">
  <img src="https://github.com/user-attachments/assets/8a628cbf-2153-4ed1-8f9e-6293114ac762" alt="Codex Indicator logo" width="112">
</p>

<h1 align="center">Codex Indicator</h1>

<p align="center">
  <strong>A compact macOS and Windows companion for Codex status, usage, and attention requests.</strong>
  <br>
  Stay focused while Codex works, then switch back when it is ready or needs you.
</p>

<p align="center">
  <a href="https://github.com/mizontheprogrammer/codex-indicator/releases/download/v1.0.1/CodexIndicatorSetup.exe"><strong>⬇ Download for Windows</strong></a>
  <br>
  <sub>Windows 10/11 · 64-bit · No Python or administrator access required</sub>
</p>

<p align="center">
  <a href="https://github.com/mizontheprogrammer/codex-indicator/releases/download/v1.0.1/CodexIndicatorSetup.exe">Installer</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/mizontheprogrammer/codex-indicator/releases/download/v1.0.1/CodexIndicator-Windows-x64.zip">Portable ZIP</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/mizontheprogrammer/codex-indicator/releases/tag/v1.0.1">Release details</a>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/db40e74b-6973-41ae-a55f-c3d42f357d61" alt="Codex Indicator showing ready, working, and needs-you states" width="900">
</p>

<p align="center">
  <em>See when Codex is ready, actively working, or waiting for your reply.</em>
</p>

Codex Indicator is a local-only desktop companion for Codex on macOS and
Windows. It watches Codex's local session records and shows a compact floating
status capsule without requiring a terminal.

> **Release status:** v1.0.1 is an early public preview.
> Release executables remain unsigned until a verified signing identity is
> available.

## macOS

The macOS build is a menu-bar/accessory application for macOS 13 Ventura or
newer. It has no normal Dock icon. The release builder produces an artifact for
the architecture of the build host and names it accurately as `arm64` or
`x86_64`; it never labels a single-architecture build as universal. Apple
Silicon and Intel are supported through their respective native builds.

### Install an unsigned development build

1. Extract `CodexIndicator-macOS-<architecture>.zip` with Finder.
2. Drag **Codex Indicator.app** to `/Applications`.
3. Control-click the application and choose **Open**, then confirm **Open**.

Development builds are not Developer ID signed or notarized. macOS may require
the Control-click flow on first launch. Do not treat them as official signed
releases. A release maintainer can follow [macOS signing and notarization](docs/MACOS_SIGNING.md).

### Menu bar and floating capsule

The monochrome menu-bar icon remains available even when the indicator is
hidden. Its menu contains Show Indicator, Hide Indicator, Reset Position,
Refresh Now, Display Mode, Sessions, Usage Details, Notification Sound, Launch
at Login, application-data/log shortcuts, About, and Quit.

The default indicator is a 300 × 48 point black capsule centered beneath the
active display's menu-bar/notch safe area. Qt positions it in logical points, so
Retina scaling does not double its size or coordinates. Display attachment,
removal, geometry changes, and active-display changes trigger repositioning and
clamping. **Position → Remember Custom Position** enables drag placement;
**Reset Position** returns to automatic top center.

The line and number always describe remaining capacity, never estimated task
completion:

1. Codex rate-limit remaining percentage, when available.
2. Context remaining percentage otherwise.
3. An em dash and a restrained indeterminate segment when unavailable while
   working.

The tooltip and Usage Details menu identify the source as `Usage remaining`,
`Context remaining`, or `Usage unavailable`. Needs-you and ready states include
text, so status is not communicated only by motion. Reduce Motion disables the
overlay animation when `respect_reduce_motion` is enabled.

With multiple sessions, the established backend priority ordering chooses the
compact session. Use the count control to expand the panel or use the Sessions
menu for an accessible list. Workspace names are elided in the panel and full
paths are available only through explicit menu actions.

### Permissions, startup, and local files

macOS asks for notification permission on first use where applicable. Denial
does not stop monitoring, the menu, or the overlay. Notification sounds can be
disabled independently. Exact cross-application window selection would require
Accessibility permission, so Codex Indicator does not request it: the session
action activates the owning application when a bundle can be identified and
otherwise offers the workspace in Finder.

Launch at Login is off by default. The current Python/PySide packaging uses a
safe per-user LaunchAgent fallback at
`~/Library/LaunchAgents/com.codexindicator.community.plist`. It requires no
administrator access, is idempotent, and removes only its own file. A future
native launcher may replace this fallback with `SMAppService`.

Configuration and logs are outside the application bundle:

```text
~/Library/Application Support/CodexIndicator/config.json
~/Library/Application Support/CodexIndicator/runtime/
```

The app reads only local Codex records under `~/.codex`, has no telemetry or
analytics, and never uploads session content. See [PRIVACY.md](PRIVACY.md).

To uninstall, quit the app, disable Launch at Login first (or remove only the
LaunchAgent file above), move the app to Trash, and optionally remove
`~/Library/Application Support/CodexIndicator/`.

### macOS developer setup, testing, and build

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python indicator.py
```

Run verification in a desktop session. For CI/headless unit tests, Qt's
offscreen backend is supported:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m bandit -q -r indicator.py app_metadata.py backend models packaging ui utils
python -m pip_audit -r requirements.txt
QT_QPA_PLATFORM=offscreen python indicator.py --smoke-test
```

Build the native artifact on the target architecture:

```bash
python packaging/build_macos.py
```

The builder creates `release/macos/Codex Indicator.app`, a ZIP, SHA-256 file,
and JSON release manifest. It bundles Python, Qt plugins, the ICNS icon, the
template menu-bar art, and legal notices. See [macOS signing and notarization](docs/MACOS_SIGNING.md)
before public distribution.

Known limitations: macOS may keep accessory windows below protected system UI;
exact terminal tab/window selection is not attempted without Accessibility
permission; and builds are architecture-specific unless every native dependency
in a universal2 build environment contains both slices.

## Windows

## Get started in three steps

1. Download `CodexIndicatorSetup.exe` using the link above.
2. Open the downloaded installer. If Windows SmartScreen appears, select
   **More info**, verify the source, and choose **Run anyway** only if the file
   came from this official repository.
3. Codex Indicator starts immediately and opens automatically the next time
   you sign in to Windows.


## Install the finished app

Download `CodexIndicatorSetup.exe` from the latest GitHub Release and run it.
The installer:

- installs the app for the current Windows user;
- creates a Start Menu shortcut and a Desktop shortcut when Windows provides a
  Desktop folder;
- enables **Start with Windows**;
- starts the app immediately;
- needs neither Python nor administrator access.

For a no-install copy, download and extract
`CodexIndicator-Windows-x64.zip`, then run `CodexIndicator.exe`. Keep the
included `Legal` directory with the EXE. Portable copies never register
themselves to start with Windows.

Release executables are currently unsigned, so Windows may show a reputation or
SmartScreen warning. Verify the download against `SHA256SUMS.txt`.

## What the indicator shows

The overlay always shows the highest-priority Codex session, its state, elapsed
time, and available usage with the reset time. Usage text is essential and
cannot be hidden. When several sessions exist, select the `+N` badge to expand
them and the minus badge to collapse them.

The amber **Needs You** state appears and stays visible when Codex:

- asks you a question or waits for a reply;
- requests network or internet access;
- requests permission to read or write outside the workspace;
- asks you to approve a command, file change, connector action, or confirmation.

After you reply or approve the request, the indicator returns to **Working**.
When the turn finishes, the indicator reads **Codex is ready**. The app plays
the notification sound again and shows a Windows tray message so you know it
is safe to switch back and review the result. Attention states read
**Codex needs you**.

Codex Indicator reads local Codex session records. It has no network client and
does not send telemetry. If Codex has not written usage information yet, the
indicator says `Usage unavailable` instead of inventing a value. See
[PRIVACY.md](PRIVACY.md) for the complete local-data description.

The backend checks known active logs every 250 milliseconds, discovers new log
files at a slower bounded interval, and sends immutable session snapshots to the
interface through Qt signals. Each read is size-bounded and multiple records are
coalesced before the interface updates. Partial Codex usage records retain the
most recent valid limits instead of replacing them with `Usage unavailable`.

### Multiple Codex sessions

Select the `+N` badge to expand the indicator and see every active session.
Select the minus badge to return to the compact single-session view.

<p align="center">
  <img src="https://github.com/user-attachments/assets/7e570f40-91e9-489f-a35d-9f1a87b1776b" alt="Expanded Codex Indicator showing multiple sessions" width="360">
</p>

<p align="center">
  <em>Expand the compact pill to review every active Codex session.</em>
</p>

## Right-click menu

Right-click either the floating indicator or its notification-area icon.

Always available:

- Show Indicator and Refresh Now
- Display mode: Normal, Low opacity, or Notifications only
- Low-opacity levels: 10%, 15%, or 25%
- Usage details and reset times
- Session actions: focus, open workspace, copy path, or remove
- Test Notification Sound
- Open App Data, Open Logs, About, and Quit

The only optional checkmark is **Notification Sound**. Official builds may
incorporate the credited Pixabay sound described in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Public source checkouts do not
contain the raw third-party MP3 and use the Windows alert as a safe fallback.

The default experience uses the compact porcelain design with monitoring active,
auto-hide disabled, and animations disabled. **Low opacity** keeps the overlay
visible at the selected subtle level for movies or full-screen work.
**Notifications only** hides the overlay while monitoring, sounds, tray
messages, and usage tracking continue normally. Select the tray icon or
**Show Indicator for 8 seconds** when you want a temporary glance.

Valid values in `config.json` are preserved rather than silently overwritten.
Windows startup is maintained only by the properly installed executable.

Settings are saved immediately in
`%LOCALAPPDATA%\CodexIndicator\config.json`. Logs and temporary session state
are kept beside that file, not in the application folder.

## Normal use

Launch **Codex Indicator** from the Desktop or Start Menu. It continues running
silently in the notification area after the floating pill hides. Clicking the
tray icon shows it again; in Notifications-only mode the preview closes again
after eight seconds. Only one copy can run at a time.

To stop it for the current session, right-click and select **Quit**. It starts
again automatically the next time you sign in to Windows.

## Uninstall

Open Start, search for **Uninstall Codex Indicator**, and run it. The uninstaller
asks whether to keep or remove settings and logs.

## Help and feedback

If something does not work, open a
[GitHub issue](https://github.com/mizontheprogrammer/codex-indicator/issues)
and include your Windows version, the app version, and the steps that caused
the problem. Do not attach Codex session files or logs before checking them for
private workspace paths or other personal information.

Preview testers can follow [the Windows beta checklist](docs/BETA_TESTING.md).

## Developer setup

The source tree is for development only:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python indicator.py
```

Run verification:

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m bandit -q -r indicator.py app_metadata.py backend models packaging ui utils
python -m pip_audit -r requirements.txt
```

Build a clean release after installing PyInstaller:

```powershell
python -m pip install -r requirements-dev.txt
python packaging\build_release.py
```

The build creates the installer, portable ZIP, checksum file, and
machine-readable release manifest in `release`. A local
`assets\notification.mp3` is incorporated when present; it is optional and
ignored by Git. See [Windows code signing](docs/CODE_SIGNING.md) before
promoting a preview as a general production release.

`config.example.json` documents the generic configuration schema. Do not commit
the generated `config.json` from `%LOCALAPPDATA%\CodexIndicator`; it can contain
workspace paths, a monitor name, and saved screen coordinates.

## License

The Codex Indicator source is licensed under the [MIT License](LICENSE). MIT
allows other people to use, copy, modify, redistribute, and sell the software as
long as they retain the required copyright and license notice.

Third-party libraries and optional media retain their own licenses. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSES](LICENSES).
