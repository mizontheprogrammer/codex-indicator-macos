"""Best-effort macOS integration using public operating-system interfaces."""

from __future__ import annotations

import ctypes
import logging

# Fixed Apple tool paths and argument lists only.
import subprocess  # nosec B404
from pathlib import Path

import psutil
from PySide6.QtGui import QGuiApplication

LOGGER = logging.getLogger(__name__)


def _objc_send(signature: object) -> object:
    library = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    return signature(("objc_msgSend", library))


def _objc_objects() -> tuple[object, object, object]:
    library = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    library.objc_getClass.restype = ctypes.c_void_p
    library.objc_getClass.argtypes = [ctypes.c_char_p]
    library.sel_registerName.restype = ctypes.c_void_p
    library.sel_registerName.argtypes = [ctypes.c_char_p]
    return library, library.objc_getClass, library.sel_registerName


def configure_accessory_application() -> bool:
    """Set NSApplication to accessory mode for source/development launches."""

    if QGuiApplication.platformName() != "cocoa":
        return False
    try:
        _, get_class, selector = _objc_objects()
        send_id = _objc_send(
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        )
        send_bool_int = _objc_send(
            ctypes.CFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long
            )
        )
        app_class = get_class(b"NSApplication")
        app = send_id(app_class, selector(b"sharedApplication"))
        return bool(send_bool_int(app, selector(b"setActivationPolicy:"), 1))
    except (AttributeError, OSError, TypeError, ValueError) as error:
        LOGGER.debug("Unable to set accessory activation policy: %s", error)
        return False


def apply_overlay_window_behavior(widget: object) -> bool:
    """Keep the overlay on Spaces/full-screen desktops without taking focus."""

    if QGuiApplication.platformName() != "cocoa":
        return False
    try:
        native_view = int(widget.winId())
        _, _, selector = _objc_objects()
        send_id = _objc_send(
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        )
        send_void_ulong = _objc_send(
            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        )
        send_void_long = _objc_send(
            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
        )
        send_void_bool = _objc_send(
            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)
        )
        window = send_id(native_view, selector(b"window"))
        if not window:
            return False
        # Public NSWindow collection behaviors: all Spaces, stationary, ignores
        # Exposé cycle, and auxiliary on an application's full-screen Space.
        behavior = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)
        send_void_ulong(window, selector(b"setCollectionBehavior:"), behavior)
        send_void_long(window, selector(b"setLevel:"), 3)  # NSFloatingWindowLevel
        send_void_bool(window, selector(b"setHidesOnDeactivate:"), False)
        return True
    except (AttributeError, OSError, TypeError, ValueError) as error:
        LOGGER.debug("Unable to apply native overlay behavior: %s", error)
        return False


def reduce_motion_enabled() -> bool:
    """Read the public Reduce Motion user default, failing closed."""

    try:
        result = subprocess.run(  # noqa: S603  # nosec B603
            [
                "/usr/bin/defaults",
                "read",
                "com.apple.universalaccess",
                "reduceMotion",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.75,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip().casefold() in {
        "1",
        "true",
        "yes",
    }


def _application_bundle(process: psutil.Process) -> Path | None:
    for candidate in (process, *process.parents()):
        try:
            executable = Path(candidate.exe()).resolve()
        except (psutil.Error, OSError):
            continue
        for parent in executable.parents:
            if parent.suffix.casefold() == ".app":
                return parent
    return None


def activate_process(pid: int) -> bool:
    """Activate the owning application via LaunchServices (`open -a`)."""

    if pid <= 0:
        return False
    try:
        process = psutil.Process(pid)
        bundle = _application_bundle(process)
        if bundle is None:
            return False
        result = subprocess.run(  # noqa: S603  # nosec B603
            ["/usr/bin/open", "-a", str(bundle)],
            capture_output=True,
            check=False,
            timeout=2.0,
        )
        return result.returncode == 0
    except (OSError, psutil.Error, subprocess.SubprocessError):
        return False


__all__ = [
    "activate_process",
    "apply_overlay_window_behavior",
    "configure_accessory_application",
    "reduce_motion_enabled",
]
