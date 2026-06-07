"""Backward-compatible OAuth entrypoint.

The auth implementation now lives under ``jules.auth``.
"""

from jules.auth import *  # noqa: F401,F403
