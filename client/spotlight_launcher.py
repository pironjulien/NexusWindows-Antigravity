"""nexus-computer backward compatibility shim for spotlight_launcher.

All implementation logic has been consolidated into core.spotlight.
This module re-exports core.spotlight symbols for 100% backward compatibility.
"""

from __future__ import annotations

import sys

import core.spotlight as _spotlight

for _name in dir(_spotlight):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_spotlight, _name)

sys.modules[__name__] = _spotlight
