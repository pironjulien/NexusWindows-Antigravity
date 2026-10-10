"""Antigravity Computer Engine root entrypoint.

Aliases to core.engine for 100% backward compatibility with tests and callers.
"""

import sys

import core.engine

sys.modules[__name__] = core.engine
