"""
numeric_core: the one place modules get Still's numeric core from.

    from numeric_core import still_core

`still_core` is the compiled C++ extension (core_cpp/, built by
`pip install -e .`) when it can be imported, otherwise the line-for-line
pure-Python port in numeric_core/reference.py. Results are identical
(see tests/test_numeric_core.py); the C++ build is simply faster.

The fallback exists because some machines can't load the extension: no
C++ toolchain, or Windows Application Control / Smart App Control
refusing an unsigned, locally built DLL.

Environment:
  STILL_NUMERIC_CORE=python   force the Python implementation
  STILL_NUMERIC_CORE=cpp      require the C++ extension (ImportError if missing)
  (unset)                     prefer C++, fall back to Python with a warning
"""

from __future__ import annotations

import logging
import os
from types import ModuleType

from . import reference as _reference

logger = logging.getLogger(__name__)

_choice = os.environ.get("STILL_NUMERIC_CORE", "").strip().lower()

still_core: ModuleType
BACKEND: str

if _choice == "python":
    still_core, BACKEND = _reference, "python"
else:
    try:
        import still_core as _compiled  # type: ignore[import-not-found]
    except ImportError as exc:
        if _choice == "cpp":
            raise
        logger.warning(
            "still_core C++ extension unavailable (%s); using the pure-Python "
            "reference implementation (identical results, slower).", exc,
        )
        still_core, BACKEND = _reference, "python"
    else:
        still_core, BACKEND = _compiled, "cpp"

__all__ = ["still_core", "BACKEND"]
