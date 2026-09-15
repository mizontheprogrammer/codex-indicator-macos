"""Domain models for Codex Indicator.

The models package contains platform-independent, serializable application
state. Backend providers and user-interface components communicate through
these types instead of sharing mutable implementation details.

Public model types are imported from their defining modules. Keeping package
initialization free of eager imports avoids circular dependencies and allows
individual modules to be tested in isolation.
"""

__all__: tuple[str, ...] = ()
