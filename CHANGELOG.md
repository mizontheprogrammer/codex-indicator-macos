# Changelog

All notable changes to Codex Indicator are documented here.

## [1.0.1] - 2026-07-26

### Fixed

- Smoke tests now use isolated temporary data and cannot change Windows startup.
- Portable and source-development runs no longer register themselves at startup.
- Normal user configuration is preserved instead of being force-overwritten.
- Log processing is bounded per poll and retains incomplete JSONL records.
- Multiple log records are coalesced into one session observation per polling cycle.
- Expired log-file state is pruned from the provider cache.
- The UI consumes coordinator snapshot signals instead of polling snapshots every 200 ms.
- Actual provider activity is shown instead of time-generated fictional activity.
- Every app, tray, shortcut, installer, and runtime-fallback surface now uses
  the current conversation-orbit logo.
- Windows shortcuts and uninstall entries now use a versioned installed icon,
  preventing Explorer and Windows Search from reusing legacy cached artwork.
- Existing shortcuts are removed before recreation so Windows cannot retain
  stale link-tracking targets from an earlier installation.
- The floating status indicator now uses an original six-link conversation
  loop instead of the Claude-like orange burst.
- Working-state accents now use Codex blue instead of orange, with automatic
  migration for existing version 1 configuration files.
- Approval-gated shell commands now trigger the “Codex needs you” state and
  notification until their matching tool result arrives.
- Windows Apps and Control Panel now expose the registered uninstaller.

### Added

- Persistent Normal, Low-opacity, and Notifications-only display modes.
- Selectable 10%, 15%, and 25% low-opacity levels for unobtrusive viewing.
- An original AI conversation-orbit app and tray logo, distinct from official
  OpenAI and ChatGPT marks.
- Windows file and product version metadata.
- Windows CI for linting, tests, security checks, packaging, and side-effect-free smoke tests.
- Tag-driven early-preview releases with checksums, a release manifest, and provenance attestation.
- Separate runtime, build, and development dependency manifests.
- Windows beta-testing checklist and privacy-safe feedback form.

### Security

- Startup persistence is restricted to the executable installed under the expected per-user installation path.

## [1.0.0] - 2026-07-25

- Initial public preview.
