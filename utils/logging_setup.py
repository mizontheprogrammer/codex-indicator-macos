"""Centralized, resilient logging configuration for Codex Indicator."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

_HANDLER_MARKER = "_codex_indicator_handler"


class UtcFormatter(logging.Formatter):
    """Render log timestamps in UTC for reliable cross-session correlation."""

    converter = time.gmtime


class BackendRecordFilter(logging.Filter):
    """Accept records produced by the backend and provider namespaces."""

    _PREFIXES = ("backend", "providers")

    def filter(self, record: logging.LogRecord) -> bool:
        return any(
            record.name == prefix or record.name.startswith(f"{prefix}.")
            for prefix in self._PREFIXES
        )


@dataclass(frozen=True, slots=True)
class LoggingPaths:
    """Resolved destinations for application log streams."""

    indicator: Path
    backend: Path
    errors: Path


@dataclass(frozen=True, slots=True)
class LoggingSetupResult:
    """Outcome of configuring logging without surfacing startup exceptions."""

    paths: LoggingPaths
    file_logging_enabled: bool
    warning: str = ""


@dataclass(slots=True)
class ExceptionHookHandle:
    """Restorable process and thread exception hooks."""

    previous_system_hook: Callable[..., Any]
    previous_thread_hook: Callable[..., Any] | None
    installed: bool = True

    def restore(self) -> None:
        """Restore hooks that were active before installation."""

        if not self.installed:
            return
        sys.excepthook = self.previous_system_hook
        if self.previous_thread_hook is not None:
            threading.excepthook = self.previous_thread_hook
        self.installed = False


def _formatter() -> UtcFormatter:
    return UtcFormatter(
        fmt=(
            "%(asctime)s.%(msecs)03dZ | %(levelname)-8s | "
            "%(process)d:%(threadName)s | %(name)s | %(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _rotating_handler(
    path: Path,
    *,
    level: int,
    maximum_bytes: int,
    backup_count: int,
) -> logging.handlers.RotatingFileHandler:
    """Create one marked UTF-8 rotating file handler."""

    handler = logging.handlers.RotatingFileHandler(
        filename=path,
        maxBytes=maximum_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    handler.setLevel(level)
    handler.setFormatter(_formatter())
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def _remove_owned_handlers(logger: logging.Logger) -> None:
    """Detach and close handlers installed by a previous configuration."""

    for handler in tuple(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except (OSError, ValueError):
                # Logging setup must remain best-effort during recovery.
                pass


def configure_logging(
    runtime_directory: str | Path,
    *,
    level: int = logging.INFO,
    maximum_bytes: int = 4 * 1024 * 1024,
    backup_count: int = 4,
    console: bool = False,
) -> LoggingSetupResult:
    """Configure application, backend, and error logs.

    Existing third-party handlers are preserved. Handlers installed by an
    earlier call to this function are replaced, making setup idempotent during
    config reloads. File-system errors trigger a stderr fallback instead of
    aborting the application.
    """

    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive")
    if backup_count < 0:
        raise ValueError("backup_count must be non-negative")

    runtime_path = Path(runtime_directory)
    paths = LoggingPaths(
        indicator=runtime_path / "indicator.log",
        backend=runtime_path / "backend.log",
        errors=runtime_path / "errors.log",
    )
    root_logger = logging.getLogger()
    _remove_owned_handlers(root_logger)
    root_logger.setLevel(level)

    try:
        runtime_path.mkdir(parents=True, exist_ok=True)

        indicator_handler = _rotating_handler(
            paths.indicator,
            level=level,
            maximum_bytes=maximum_bytes,
            backup_count=backup_count,
        )
        backend_handler = _rotating_handler(
            paths.backend,
            level=level,
            maximum_bytes=maximum_bytes,
            backup_count=backup_count,
        )
        backend_handler.addFilter(BackendRecordFilter())
        error_handler = _rotating_handler(
            paths.errors,
            level=logging.ERROR,
            maximum_bytes=maximum_bytes,
            backup_count=backup_count,
        )

        root_logger.addHandler(indicator_handler)
        root_logger.addHandler(backend_handler)
        root_logger.addHandler(error_handler)

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(_formatter())
            setattr(console_handler, _HANDLER_MARKER, True)
            root_logger.addHandler(console_handler)

        result = LoggingSetupResult(
            paths=paths,
            file_logging_enabled=True,
        )
        logging.getLogger(__name__).info(
            "Logging initialized in %s",
            runtime_path,
        )
        return result
    except (OSError, ValueError) as error:
        _remove_owned_handlers(root_logger)
        fallback = logging.StreamHandler()
        fallback.setLevel(level)
        fallback.setFormatter(_formatter())
        setattr(fallback, _HANDLER_MARKER, True)
        root_logger.addHandler(fallback)

        warning = f"File logging unavailable in {runtime_path}: {error}"
        root_logger.warning(warning)
        return LoggingSetupResult(
            paths=paths,
            file_logging_enabled=False,
            warning=warning,
        )


def install_exception_hooks(
    logger: logging.Logger | None = None,
) -> ExceptionHookHandle:
    """Log otherwise uncaught main-thread and worker-thread exceptions."""

    target_logger = logger or logging.getLogger("errors")
    previous_system_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def system_hook(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        if issubclass(exception_type, KeyboardInterrupt):
            previous_system_hook(exception_type, exception, traceback)
            return
        target_logger.critical(
            "Unhandled exception on the main thread",
            exc_info=(exception_type, exception, traceback),
        )

    def thread_hook(arguments: threading.ExceptHookArgs) -> None:
        if issubclass(arguments.exc_type, KeyboardInterrupt):
            if previous_thread_hook is not None:
                previous_thread_hook(arguments)
            return
        target_logger.critical(
            "Unhandled exception on worker thread %s",
            getattr(arguments.thread, "name", "unknown"),
            exc_info=(
                arguments.exc_type,
                arguments.exc_value,
                arguments.exc_traceback,
            ),
        )

    sys.excepthook = system_hook
    if previous_thread_hook is not None:
        threading.excepthook = thread_hook

    return ExceptionHookHandle(
        previous_system_hook=previous_system_hook,
        previous_thread_hook=previous_thread_hook,
    )


def shutdown_logging() -> None:
    """Flush and close only the handlers owned by Codex Indicator."""

    root_logger = logging.getLogger()
    for handler in tuple(root_logger.handlers):
        if not getattr(handler, _HANDLER_MARKER, False):
            continue
        try:
            handler.flush()
        except (OSError, ValueError):
            pass
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except (OSError, ValueError):
            pass


__all__ = [
    "BackendRecordFilter",
    "ExceptionHookHandle",
    "LoggingPaths",
    "LoggingSetupResult",
    "UtcFormatter",
    "configure_logging",
    "install_exception_hooks",
    "shutdown_logging",
]
