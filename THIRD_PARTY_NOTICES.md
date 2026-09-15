# Third-Party Notices

Codex Indicator contains or is built with third-party software and media. Those
components are licensed by their respective owners under the terms listed
below. They are not relicensed under the Codex Indicator MIT License.

## Qt for Python: PySide6 and Shiboken6 6.10.2

- Project: https://doc.qt.io/qtforpython-6/
- Source: https://code.qt.io/cgit/pyside/pyside-setup.git/
- License expression published by the Python packages:
  `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
- License information: https://doc.qt.io/qtforpython-6/licenses.html
- Local PySide notice: `LICENSES/Qt-PySide6-NOTICE.txt`
- Complete LGPL 3.0 text: `LICENSES/LGPL-3.0.txt`
- Complete GPL 3.0 text incorporated by LGPL 3.0:
  `LICENSES/GPL-3.0.txt`

Codex Indicator uses these components under the LGPL 3.0 option. The complete
application source and build script are distributed so recipients can rebuild
the application with a compatible or modified Qt for Python installation.
Nothing in the Codex Indicator license restricts reverse engineering needed to
debug modifications to the LGPL-covered libraries.

## psutil 7.2.2

- Project and source: https://github.com/giampaolo/psutil
- License: BSD 3-Clause
- Local license copy: `LICENSES/psutil-BSD-3-Clause.txt`

## pywin32 312

- Project and source: https://github.com/mhammond/pywin32
- License: PSF/BSD-style licenses
- Local license copy: `LICENSES/pywin32-BSD.txt`

## PyInstaller 6.16.0

- Project and source: https://github.com/pyinstaller/pyinstaller
- License: GPL 2.0-or-later with the PyInstaller bootloader exception
- License information:
  https://pyinstaller.org/en/stable/license.html

PyInstaller is a build tool rather than an application runtime API. Its
bootloader and related files are included in Windows and macOS executables under the
PyInstaller bootloader exception. The release builder copies the exact
PyInstaller `COPYING.txt` installed in the build environment into every release
package.

## Optional notification sound

Official builds may incorporate:

- **Positive Notification Alert**
- Creator: Universfield
- Source:
  https://pixabay.com/sound-effects/film-special-effects-positive-notification-alert-351299/
- License: Pixabay Content License
  https://pixabay.com/service/license-summary/

The audio is incorporated into the compiled application and is not offered as a
standalone source asset. It is not covered by the Codex Indicator MIT License.
Source builds without the optional audio use a Windows system notification sound
or the macOS Glass system sound.

## OpenAI names

OpenAI and Codex are trademarks or product names of OpenAI. Their use here is
solely descriptive. Codex Indicator is an unofficial community project and is
not affiliated with, endorsed by, or supported by OpenAI.
