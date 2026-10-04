"""Config package.

The public config surface (``JunctionConfig`` and the path helpers) is exposed
lazily via :pep:`562` ``__getattr__`` so that importing a lightweight submodule
such as :mod:`junction.config.paths` does NOT eagerly pull in the heavy
``junction.config.loader`` (DTOs, schema validation, the process-global cache,
and the lazily-imported provider factory). ``from junction.config import X``
continues to work for every name in ``__all__`` — it just resolves on first
access instead of at package import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "JunctionConfig",
    "config_dir",
    "config_local_path",
    "config_path",
    "data_home",
    "ensure_data_home",
    "env_path",
    "resolve_agent_config_path",
]

if TYPE_CHECKING:  # imported for type checkers only; no runtime loader import
    from junction.config.loader import (
        JunctionConfig,
        config_dir,
        config_local_path,
        config_path,
        data_home,
        ensure_data_home,
        env_path,
        resolve_agent_config_path,
    )


def __getattr__(name: str) -> object:
    """Resolve public config names lazily from the loader (PEP 562)."""
    if name in __all__:
        # circular import: config.loader imports from junction.config.paths,
        # which triggers this package __init__ — a top-level import of loader
        # here would create an init <-> loader runtime cycle AND eagerly pull the
        # heavy loader in whenever the config package is touched (including from
        # the lightweight config.paths leaf), defeating this PEP 562 lazy seam.
        from junction.config import loader

        return getattr(loader, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
