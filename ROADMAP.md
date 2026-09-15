# Codex Indicator — Target Implementation Roadmap

Codex Indicator targets a production-grade Windows desktop overlay for
monitoring one or more Codex sessions. This roadmap defines the intended
architecture, quality gates, and acceptance criteria; it is not a claim that
every criterion is already complete.

## 1. Product principles

- Windows-first behavior with graceful degradation when optional APIs are
  unavailable.
- A responsive event-driven UI backed by bounded polling and file-system
  observation.
- Provider-neutral session tracking so future Codex hooks can be added without
  changing the UI or session store.
- Durable, atomic JSON persistence that survives interrupted writes and malformed
  third-party data.
- No uncaught exception may terminate the indicator. Failures are isolated,
  logged, retried with backoff where appropriate, and reflected through a safe
  fallback state.
- A fully custom-painted, high-DPI-aware interface with no stock Qt widget
  styling exposed to the user.

## 2. Target repository

```text
codex-indicator/
├── indicator.py
├── install.py
├── config.json
├── requirements.txt
├── README.md
├── ROADMAP.md
├── LICENSE
├── backend/
│   ├── __init__.py
│   ├── coordinator.py
│   ├── session_store.py
│   ├── stale_monitor.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       ├── ipc_provider.py
│       ├── log_provider.py
│       ├── stream_provider.py
│       └── hook_provider.py
├── models/
│   ├── __init__.py
│   ├── config.py
│   ├── events.py
│   └── session.py
├── ui/
│   ├── __init__.py
│   ├── animations.py
│   ├── overlay.py
│   ├── palette.py
│   ├── painter.py
│   └── windows_effects.py
├── utils/
│   ├── __init__.py
│   ├── atomic_json.py
│   ├── logging_setup.py
│   ├── process_utils.py
│   ├── sound.py
│   └── windows.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_atomic_json.py
│   ├── test_config.py
│   ├── test_coordinator.py
│   ├── test_log_provider.py
│   ├── test_session.py
│   └── test_session_store.py
└── runtime/
    ├── .gitkeep
    └── sessions/
        └── .gitkeep
```

Runtime log files and session JSON files are generated locally and excluded from
source control.

## 3. Architecture

### 3.1 Domain model

`models/session.py` defines the canonical session record:

- stable session ID
- workspace path
- state: `READY`, `WORKING`, or `NEEDS_YOU`
- state start time and last activity time in timezone-aware UTC
- process ID
- terminal window handle
- window title
- provider identity and optional human-readable activity

The model owns validation, serialization, elapsed-time calculation, priority
ordering, and safe normalization of external data. State changes produce typed
events rather than mutating UI objects directly.

### 3.2 Configuration

`models/config.py` loads `config.json` into typed, validated dataclasses. Unknown
keys remain forward-compatible, invalid values fall back individually, and a
broken file is backed up before defaults are restored.

Configuration covers:

- focused-process auto-hide rules
- polling and provider intervals
- theme, opacity, dimensions, spacing, typography, and colors
- animation and sound switches
- saved screen-relative position
- activity labels
- working, stale, and dead-session timeouts
- provider enablement and provider-specific paths

### 3.3 Provider layer

All providers implement the interface in `backend/providers/base.py` and emit
normalized session observations:

- `LogProvider` tails configured Codex logs incrementally, handles rotation, and
  maps configurable patterns to the three states.
- `IpcProvider` consumes atomic JSON session files in `runtime/sessions`.
- `StreamProvider` supplies a reusable parser and subprocess/pipe adapter for
  monitored stdin/stdout streams without blocking the UI thread.
- `HookProvider` is a functional future-hook adapter that accepts normalized
  events through a stable Python interface.

Providers never update widgets or persistence directly.

### 3.4 Coordination and persistence

`BackendCoordinator` runs providers on Qt-managed worker threads, merges
observations by session ID, rejects out-of-order updates, and emits a single
immutable snapshot to the UI.

`SessionStore` persists one JSON file per session using same-volume temporary
files, flush, optional disk synchronization, and atomic replacement. Corrupt
files are quarantined. It reconciles process liveness, stale sessions, and
provider updates without deleting potentially recoverable data prematurely.

### 3.5 Windows integration

The Windows utility layer:

- enumerates Codex and terminal processes with `psutil`
- resolves foreground process names and native window handles with `pywin32`
- restores and focuses a session window using safe foreground-window rules
- registers optional current-user startup entries
- creates Start Menu and desktop shortcuts
- invokes the configured Windows notification sound

Every native feature has a logged fallback path.

### 3.6 User interface

The overlay is a frameless, tool-style, always-on-top Qt window. Its complete
surface is custom-painted:

- translucent rounded acrylic or mica-compatible background where supported
- dark fallback background on unsupported systems
- soft shadow and subtle border
- per-session colored state mark, status/activity, workspace, and elapsed timer
- rotating spark for working sessions
- pulsing amber treatment for attention-required sessions
- smooth layout, opacity, and appearance transitions
- drag handling with screen-bound clamping and debounced position persistence
- click-to-focus session rows

Rows are sorted by `NEEDS_YOU`, then `WORKING`, then `READY`, with most recent
activity breaking ties.

The overlay auto-hides when a configured development terminal/editor process owns
the foreground window, unless at least one session needs attention.

## 4. Delivery milestones and file order

Each file is delivered individually and reviewed before the next file is added.
Package marker files are intentionally included because the finished repository
must contain every required file.

### Milestone 0 — Specification and repository metadata

1. `ROADMAP.md`
2. `LICENSE`
3. `requirements.txt`
4. `.gitignore`

Gate: dependency versions, supported platform, licensing, generated artifacts,
and delivery scope are explicit.

### Milestone 1 — Models and safe primitives

5. `models/__init__.py`
6. `models/session.py`
7. `models/events.py`
8. `models/config.py`
9. `utils/__init__.py`
10. `utils/atomic_json.py`
11. `utils/logging_setup.py`
12. `config.json`

Gate: model/config round trips, validation, status priority, and atomic-write
failure behavior are covered by tests.

### Milestone 2 — Windows and operating-system services

13. `utils/process_utils.py`
14. `utils/windows.py`
15. `utils/sound.py`

Gate: missing processes, invalid handles, privilege boundaries, unavailable
native APIs, and non-Windows test environments fail safely.

### Milestone 3 — Provider framework

16. `backend/__init__.py`
17. `backend/providers/__init__.py`
18. `backend/providers/base.py`
19. `backend/providers/ipc_provider.py`
20. `backend/providers/log_provider.py`
21. `backend/providers/stream_provider.py`
22. `backend/providers/hook_provider.py`

Gate: all providers emit the same event contract, can stop promptly, isolate
malformed input, and never block the UI thread.

### Milestone 4 — Session lifecycle and orchestration

23. `backend/session_store.py`
24. `backend/stale_monitor.py`
25. `backend/coordinator.py`

Gate: multi-provider merge order, dead-process cleanup, stale transitions,
atomic persistence, retry behavior, and orderly shutdown are deterministic.

### Milestone 5 — Visual system and Windows effects

26. `ui/__init__.py`
27. `ui/palette.py`
28. `ui/animations.py`
29. `ui/windows_effects.py`
30. `ui/painter.py`
31. `ui/overlay.py`

Gate: the interface scales at 100–250% DPI, remains inside the available screen,
has correct state priority and attention override behavior, and degrades cleanly
without acrylic effects.

### Milestone 6 — Application lifecycle

32. `indicator.py`

Gate: single-instance protection, logging, config recovery, backend startup,
tray/overlay lifecycle, exception containment, and graceful shutdown work
together.

### Milestone 7 — Installation and removal

33. `install.py`
34. `runtime/.gitkeep`
35. `runtime/sessions/.gitkeep`

Gate: install, upgrade, startup registration, shortcuts, config backup, and
uninstall are idempotent and do not remove user configuration without explicit
consent.

### Milestone 8 — Automated verification

36. `tests/__init__.py`
37. `tests/conftest.py`
38. `tests/test_session.py`
39. `tests/test_config.py`
40. `tests/test_atomic_json.py`
41. `tests/test_log_provider.py`
42. `tests/test_session_store.py`
43. `tests/test_coordinator.py`

Gate: the suite passes on Python 3.12, with Windows-only behavior mocked where
required. Static compilation and import smoke tests pass.

### Milestone 9 — Documentation and release readiness

44. `README.md`

Gate: a clean-machine user can install, launch, configure providers, troubleshoot,
and uninstall the application using the documentation alone. Architecture, data
formats, security considerations, FAQ, and screenshot placeholders are complete.

## 5. Verification strategy

Every implementation file is checked as it is delivered. Relevant checks include:

- Python bytecode compilation
- import smoke tests
- unit tests with deterministic clocks and temporary directories
- type-oriented review of public interfaces
- malformed JSON and interrupted-write fault injection
- synthetic log rotation and partial-line parsing
- process exit, PID reuse, stale heartbeat, and duplicate provider scenarios
- native-window calls with invalid and disappearing handles
- high-DPI visual rendering at common Windows scale factors
- long workspace names, many concurrent sessions, and empty-session layout
- sound disabled, missing sound alias, and inaccessible runtime directory cases
- clean install, in-place upgrade, retained-config uninstall, and full removal

## 6. Definition of done

The project is complete only when:

- all listed files exist and contain production-quality implementations
- the application runs on supported Windows 10/11 systems with Python 3.12+
- all three states render and animate correctly
- multiple sessions are tracked, prioritized, persisted, and focusable
- auto-hide and attention override behave as configured
- runtime writes are atomic and corrupt data cannot crash the process
- dead and stale sessions are handled automatically
- optional Windows effects and sounds have safe fallbacks
- installer operations are idempotent and reversible
- automated tests and compile/import checks pass
- README installation, configuration, architecture, troubleshooting, and FAQ
  sections match the shipped behavior
