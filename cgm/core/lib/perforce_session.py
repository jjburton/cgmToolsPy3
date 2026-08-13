"""
------------------------------------------
perforce_session: cgm.core.lib.perforce_session
Session buffer for Perforce status queries.

Survives reload of cgm.core.lib.perforce and cgmP4 tool opens.

Flush in Script Editor (py2/py3 via cgmGEN._reloadMod):

    import cgm.core.lib.perforce_session as P4SESSION
    import cgm.core.cgm_General as cgmGEN
    cgmGEN._reloadMod(P4SESSION)

Or call P4UTIL.reload_session_cache() / P4UTIL.flush_status_cache().
------------------------------------------
"""

# Session cache — module globals intentionally persist for Maya session lifetime.
_CACHE = {
    'p4_user': None,
    'p4_client': None,
    'available': None,
    'info': None,
    'connection_report': None,
    'connection_report_key': None,
}


def clear():
    """Flush all session P4 status/query caches."""
    for _key in _CACHE:
        _CACHE[_key] = None
