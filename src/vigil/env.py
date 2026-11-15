"""Environment variable lookup with a deprecated ``TEAMMATE_*`` fallback.

Settings are read from ``VIGIL_<NAME>``. If that is unset, the old
``TEAMMATE_<NAME>`` is read for one more release and a
``DeprecationWarning`` names the variable to rename. ``VIGIL_<NAME>`` wins
when both are set. An empty value counts as unset, as before.
"""

from __future__ import annotations

import os
import warnings

_NEW = "VIGIL_"
_OLD = "TEAMMATE_"


def get(name: str, default: str | None = None) -> str | None:
    """Return ``VIGIL_<name>``, else deprecated ``TEAMMATE_<name>``, else ``default``."""
    value = os.environ.get(_NEW + name)
    if value is not None:
        return value
    legacy = os.environ.get(_OLD + name)
    if legacy is not None:
        warnings.warn(
            f"{_OLD}{name} is deprecated and will be removed in the next release; "
            f"set {_NEW}{name} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy
    return default
