"""cgm.lib — vendored trees plus the lists shim.

First-party Maya helpers were parked in ``cgm.libOld`` (Spring Cleaning probe).
``from cgm.lib import attributes`` and the other old first-party modules will
fail until those files are shimmed here or callers retarget ``cgm.core``.

Still here: ``lists`` (shim), ``cgmBaseMelUI`` (zoo re-export), ``zoo`` / ``ml`` /
``bo`` / ``openSource``.
"""
