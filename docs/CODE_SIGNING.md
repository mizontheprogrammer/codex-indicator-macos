# Windows code signing

Codex Indicator release artifacts are currently unsigned. Checksums and GitHub
artifact attestations improve integrity verification, but they do not replace
Authenticode publisher identity or Windows reputation.

## Supported release paths

Choose one before describing a release as generally production-ready:

1. Publish an MSIX through Microsoft Store so Microsoft signs the distributed
   package.
2. Obtain an eligible trusted code-signing service/certificate and sign the app,
   installer, and uninstaller in the release workflow.
3. Apply to a reputable free signing program for qualifying open-source
   projects.

Do not place a private signing key in the repository or in a normal GitHub
secret. Prefer a managed signing service with short-lived workload identity.

## Required release order

1. Build from a protected version tag in GitHub Actions.
2. Sign `CodexIndicator.exe`.
3. Build the installer around the signed application.
4. Sign and timestamp `CodexIndicatorSetup.exe`.
5. Verify every signature with `Get-AuthenticodeSignature`.
6. Generate checksums, manifest, SBOM, and provenance after final signing.
7. Smoke-test the exact signed artifacts.

The current `release.yml` intentionally publishes v1.0.1 as an **early
preview**. Add signing only after the maintainer has a verified signing identity.
