"""Optional Windows acrylic blur for a native Qt window."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

LOGGER = logging.getLogger(__name__)


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def enable_acrylic(hwnd: int, *, tint_abgr: int = 0xCC1D1917) -> bool:
    """Enable acrylic blur when supported, returning success."""

    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        setter = user32.SetWindowCompositionAttribute
        setter.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_WindowCompositionAttributeData),
        ]
        setter.restype = wintypes.BOOL
        policy = _AccentPolicy(
            AccentState=4,  # ACCENT_ENABLE_ACRYLICBLURBEHIND
            AccentFlags=2,
            GradientColor=tint_abgr,
            AnimationId=0,
        )
        data = _WindowCompositionAttributeData(
            Attribute=19,  # WCA_ACCENT_POLICY
            Data=ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            SizeOfData=ctypes.sizeof(policy),
        )
        return bool(setter(hwnd, ctypes.byref(data)))
    except (AttributeError, OSError, TypeError) as error:
        LOGGER.debug("Acrylic effect unavailable: %s", error)
        return False


__all__ = ["enable_acrylic"]
