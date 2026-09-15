# Assets

`codex_indicator.ico` is the multi-size Windows application, shortcut, and tray
icon. `codex_indicator_logo.png` is its transparent high-resolution source for
documentation and future icon exports. The original conversation-orbit design
was generated specifically for this community project and is intentionally
distinct from official OpenAI and ChatGPT marks.

`CodexIndicator.icns` is the macOS application icon and
`CodexIndicatorTemplate.png` is the monochrome menu-bar artwork. Both are
deterministically derived from `codex_indicator_logo.png` by
`packaging/generate_macos_assets.py`; no third-party logo is downloaded.

An optional local file named `notification.mp3` may be placed in this directory
before building. It is intentionally excluded from the public source repository
so that a third-party stock sound is not redistributed as a standalone asset.
When the file is absent, the application uses the configured Windows system
alert or the licensed macOS Glass system sound.

Official release builds may incorporate the following sound into the compiled
application:

- **Positive Notification Alert** by Universfield
- Source: https://pixabay.com/sound-effects/film-special-effects-positive-notification-alert-351299/
- License: Pixabay Content License
  https://pixabay.com/service/license-summary/

That sound remains subject to the Pixabay Content License and is not covered by
the project's MIT License.
