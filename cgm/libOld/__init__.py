"""Parked first-party ``cgm.lib`` modules (Spring Cleaning probe).

These files still import each other as ``from cgm.lib import …``. They are not
a drop-in package — leftover tools that imported ``cgm.lib.X`` will raise
``ImportError`` until they retarget ``cgm.core`` or a shim lands back in
``cgm.lib``.
"""
