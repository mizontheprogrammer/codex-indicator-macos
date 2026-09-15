# macOS signing and notarization

The macOS builder intentionally supports unsigned development builds. A public
release should be signed with a **Developer ID Application** identity, submitted
to Apple's notary service, stapled, and verified. Never commit certificates,
private keys, Apple credentials, app-specific passwords, profiles, or exported
keychains.

Start with a clean architecture-specific build:

```bash
python packaging/build_macos.py
APP="release/macos/Codex Indicator.app"
IDENTITY="Developer ID Application: Example Company (TEAMID)"
```

Sign nested Mach-O binaries from the inside out. The following loop detects
binaries rather than trusting filename extensions:

```bash
find "$APP/Contents/Frameworks" -type f -print0 | while IFS= read -r -d '' file; do
  if file "$file" | grep -q 'Mach-O'; then
    codesign --force --options runtime --timestamp --sign "$IDENTITY" "$file"
  fi
done

find "$APP/Contents/Frameworks" -type d -name '*.framework' -print0 \
  | sort -zr \
  | while IFS= read -r -d '' framework; do
      codesign --force --options runtime --timestamp --sign "$IDENTITY" "$framework"
    done

codesign --force --options runtime --timestamp --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=4 "$APP"
```

The app needs no special entitlements for its default features. If future work
adds entitlements, review them explicitly and sign every nested item and the app
with the same hardened-runtime policy.

Create a notarization ZIP after signing:

```bash
ditto -c -k --sequesterRsrc --keepParent "$APP" \
  "release/macos/CodexIndicator-macOS-notarization.zip"
```

Store credentials in Keychain once, outside the repository:

```bash
xcrun notarytool store-credentials "codex-indicator-notary" \
  --apple-id "release@example.com" \
  --team-id "TEAMID" \
  --password "APP-SPECIFIC-PASSWORD"
```

Submit, wait, staple, and assess Gatekeeper:

```bash
xcrun notarytool submit \
  "release/macos/CodexIndicator-macOS-notarization.zip" \
  --keychain-profile "codex-indicator-notary" \
  --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=4 "$APP"
codesign -dv --verbose=4 "$APP"
```

Recreate the user-facing ZIP and its checksums after stapling; stapling changes
the bundle. Do not mark the JSON manifest as Developer ID signed or notarized
until all verification commands succeed.
