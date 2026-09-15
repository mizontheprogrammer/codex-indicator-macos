# v1.0.1 Windows beta plan

Do not call v1.0.1 production-ready until at least 20 external Windows users
complete this checklist.

## Coverage targets

- 10 Windows 11 installer users
- 3 Windows 10 installer users
- 3 portable-ZIP users
- 2 multi-monitor/high-DPI users
- 2 users running three or more simultaneous Codex tasks

## Tester checklist

1. Download only from the GitHub release and compare `SHA256SUMS.txt`.
2. Install or extract the app.
3. Restart Windows and confirm only an installed copy starts automatically.
4. Confirm a portable copy does not replace the installed startup entry.
5. Run a Codex task to completion and verify “Codex is ready.”
6. Trigger a permission or reply request and verify “Codex needs you.”
7. Confirm the notification sound is heard once, without repeated alerts.
8. Confirm usage and reset time update after Codex writes rate-limit data.
9. Exercise multiple sessions and multiple monitors.
10. Record idle CPU/memory after five minutes.
11. Uninstall and confirm the user-data choice is respected.

Submit results with the **Windows beta feedback** GitHub issue form. Never attach
raw Codex session logs or private conversation content.
