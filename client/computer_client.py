"""nexus-computer backward compatibility shim for computer_client.

All implementation logic has been consolidated into core.engine.
This module re-exports core.engine symbols for 100% backward compatibility.
"""

from __future__ import annotations

import sys

import core.engine as _engine

# Re-export all public and internal engine symbols
for _name in dir(_engine):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_engine, _name)

# Module alias
sys.modules[__name__] = _engine
