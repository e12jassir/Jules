"""Desktop environment integration — not implemented yet.

This module is a placeholder for future desktop-level integrations
(notifications beyond freedesktop.org's `notify-send`, window/session
awareness, etc.). No specific desktop environment or IPC mechanism is
committed to here.

Decision (2026-07-18): Jules targets any Linux distribution, not a fixed
desktop environment. When this module gets real content, the implementation
must be selected based on what is actually detected at runtime (e.g. is
D-Bus available? is there a session bus? which desktop portal responds?)
rather than assuming KDE/KWin or any other specific stack. See ROADMAP.md
Fase 2 for the scoping of this work.
"""

from __future__ import annotations
