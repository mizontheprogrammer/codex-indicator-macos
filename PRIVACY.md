# Privacy

Codex Indicator is a local macOS and Windows desktop utility. It has no telemetry,
analytics, advertising SDK, account system, or network client, and it does not
upload Codex data.

## Data the application reads

To determine local task status, usage, and whether attention is needed, the
application reads Codex session records and logs under the current user's
`.codex` directory. Records are processed locally and may contain task
activity, workspace paths, usage values, and permission or reply requests.

When a structured attention event is unavailable, reply detection may inspect
assistant message text in memory. The application does not copy or retain those
message bodies. It stores only the derived session state needed by the
indicator, such as session identifiers, workspace information, status,
timestamps, and usage values.

## Data the application stores

On macOS, settings, derived session state, and diagnostic logs are stored under:

```text
~/Library/Application Support/CodexIndicator
```

On Windows they are stored under:

```text
%LOCALAPPDATA%\CodexIndicator
```

Workspace names or paths can therefore appear in local settings, session state,
or diagnostic logs. These files remain on the computer and are not transmitted
by Codex Indicator.

The uninstaller asks whether this local data should also be removed. Users can
inspect or delete the directory at any time after quitting the application.

## Windows integration

The installer creates per-user shortcuts and a per-user Windows startup entry.
It does not require administrator privileges. The app uses local-only Windows
inter-process communication to ensure that only one indicator instance runs.

## macOS integration

The app uses Qt's public menu-bar and notification APIs. It can use the public
LaunchServices `open` interface to activate an identified owning application or
show a workspace in Finder. It does not request Accessibility permission for
exact cross-application window control. Launch at Login is opt-in and creates
only `~/Library/LaunchAgents/com.codexindicator.community.plist`.

## Third-party services

Codex Indicator is an unofficial community project. It is not affiliated with,
endorsed by, or supported by OpenAI. OpenAI's own products and services are
governed by OpenAI's separate terms and privacy policy.

Security or privacy concerns can be reported through the repository's GitHub
security-advisory feature after the project is published.
