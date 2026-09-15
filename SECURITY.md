# Security Policy

## Supported versions

| Version | Status |
|---|---|
| 1.0.1 preview | Receives security fixes |
| 1.0.0 | Unsupported; upgrade to 1.0.1 |

Security fixes are applied to the newest preview or stable release. Preview
builds are not a promise of enterprise support.

## Reporting a vulnerability

After the repository is published, use GitHub's private security-advisory
feature to report vulnerabilities. Do not include sensitive Codex session data,
conversation content, credentials, or private workspace files in a public
issue.

Include the affected version, Windows version, reproduction steps, and the
security impact. A maintainer should acknowledge a complete report within seven
days and coordinate disclosure after a fix or mitigation is available.

## Security model

Codex Indicator is a local, per-user desktop utility. It does not require
administrator privileges and does not contain a network client or telemetry.
It reads local Codex session records and stores derived state under
`%LOCALAPPDATA%\CodexIndicator`.

Release checksums are published in `SHA256SUMS.txt`. Windows executables should
be treated as unsigned until a release explicitly identifies a code-signing
certificate.
