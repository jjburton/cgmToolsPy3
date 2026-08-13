"""
------------------------------------------
perforce: cgm.core.lib.perforce
Read-only Perforce connectivity queries for cgmTools.

Server calls use explicit p4 -u USER -c CLIENT (-ztag), not registry/cwd discovery.
Optional layer — does not alter export/save unless explicitly wired later.
Reference only: cgm.lib.zoo.zooPy.perforce (never import from cgm core).
------------------------------------------
"""
# From Python =============================================================
import logging
import os
import re
import subprocess
import sys

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Windows: p4.exe is a console app — hide subprocess windows in Maya
_P4_SUBPROCESS_KW = {}
if sys.platform == 'win32':
    _P4_SUBPROCESS_KW['creationflags'] = subprocess.CREATE_NO_WINDOW

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGEN
import cgm.core.lib.perforce_session as P4SESSION

# Session cache lives in perforce_session (survives perforce.py reload).
_cache = P4SESSION._CACHE

_INFO_PREFIX_RE = re.compile(r'^info\d*:\s*', re.IGNORECASE)

# Maya optionVars — shared prefs for all cgm P4 tools
OPT_P4_USER = 'cgmVar_p4_user'
OPT_P4_CLIENT = 'cgmVar_p4_client'

# p4 changes (text): Change 12345 on YYYY/MM/DD by user@client *pending*
_CHANGE_LINE_RE = re.compile(
    r'^Change\s+(?P<change>\d+)\s+on\s+\S+\s+by\s+\S+@\S+\s+\*(?P<status>\w+)\*'
)


#>>> Internal helpers
#===================================================================
def _strip_info_prefix(line):
    return _INFO_PREFIX_RE.sub('', line.rstrip('\r\n'))


def resolve_connection(p4_user=None, p4_client=None):
    """
    Resolve Perforce user and client workspace.

    Priority: explicit args, cgm optionVars, CGM_P4* env, P4* env.
    Empty strings are treated as unset (fall through to optionVars / env).
    """
    if not p4_user or not p4_client:
        _ov_user, _ov_client = get_connection_prefs()
        if not p4_user:
            p4_user = _ov_user
        if not p4_client:
            p4_client = _ov_client

    _user = p4_user or os.environ.get('CGM_P4USER') or os.environ.get('P4USER')
    _client = p4_client or os.environ.get('CGM_P4CLIENT') or os.environ.get('P4CLIENT')
    return _user, _client


def get_connection_prefs():
    """Read p4 user/client from Maya optionVars."""
    try:
        import cgm.core.cgm_Meta as cgmMeta
        _u = cgmMeta.cgmOptionVar(OPT_P4_USER, varType='string', defaultValue='')
        _c = cgmMeta.cgmOptionVar(OPT_P4_CLIENT, varType='string', defaultValue='')
        _user = (_u.getValue() or '').strip() or None
        _client = (_c.getValue() or '').strip() or None
        return _user, _client
    except Exception:
        return None, None


def save_connection_prefs(p4_user=None, p4_client=None):
    """Persist p4 user/client to Maya optionVars."""
    import cgm.core.cgm_Meta as cgmMeta
    if p4_user is not None:
        cgmMeta.cgmOptionVar(OPT_P4_USER, varType='string', defaultValue='').setValue(
            str(p4_user).strip())
    if p4_client is not None:
        cgmMeta.cgmOptionVar(OPT_P4_CLIENT, varType='string', defaultValue='').setValue(
            str(p4_client).strip())
    _clear_cache()


def _clear_cache():
    P4SESSION.clear()


def flush_status_cache():
    """Clear all session P4 status/query caches (writes, Refresh — in-place, no module reload)."""
    P4SESSION.clear()


def reload_session_cache():
    """Reload perforce_session to flush buffer. Uses cgmGEN._reloadMod (py2/py3)."""
    cgmGEN._reloadMod(P4SESSION)
    global _cache
    _cache = P4SESSION._CACHE


def _connection_report_cache_key(p4_user, p4_client, scene_path):
    return (p4_user or '', p4_client or '', scene_path or '')


def _get_cached_connection_report(key):
    if _cache.get('connection_report_key') == key and _cache.get('connection_report') is not None:
        return dict(_cache['connection_report'])
    return None


def _set_cached_connection_report(key, report):
    _cache['connection_report_key'] = key
    _cache['connection_report'] = report


def _project_status_from_report(report):
    """Build Project UI status dict from a cached query_connection report."""
    _report = report or {}
    _conn = _report.get('connection') or {}
    _user = _report.get('p4User')
    _client = _report.get('p4Client')

    if not _user or not _client:
        return {
            'connected': False,
            'label': 'P4: not connected — set user/client in cgmP4',
            'reason': _report.get('reason') or 'missing credentials',
        }

    if not _report.get('connected'):
        _reason = _report.get('reason') or _conn.get('reason') or 'unknown'
        return {
            'connected': False,
            'label': 'P4: not connected — {0}'.format(_reason),
            'reason': _reason,
        }

    _uname = _conn.get('userName') or _user
    _cname = _conn.get('clientName') or _client
    return {
        'connected': True,
        'label': 'P4: {0} @ {1}'.format(_uname, _cname),
        'connection': _conn,
    }


def _info_cache_matches(p4_user, p4_client):
    return (
        _cache.get('p4_user') == p4_user
        and _cache.get('p4_client') == p4_client
        and _cache.get('available') is not None
    )


def _project_status_from_info_cache(p4_user, p4_client):
    """Build Project UI status from warm is_available / connection_info session cache."""
    if not _info_cache_matches(p4_user, p4_client):
        return None
    if not _cache.get('available'):
        return {
            'connected': False,
            'label': 'P4: not connected — p4 info failed',
            'reason': 'p4 info failed',
        }
    _info = connection_info(force=False, p4_user=p4_user, p4_client=p4_client)
    if not _info.get('connected'):
        _reason = _info.get('reason') or 'unknown'
        return {
            'connected': False,
            'label': 'P4: not connected — {0}'.format(_reason),
            'reason': _reason,
        }
    _uname = _info.get('userName') or p4_user
    _cname = _info.get('clientName') or p4_client
    return {
        'connected': True,
        'label': 'P4: {0} @ {1}'.format(_uname, _cname),
        'connection': _info,
    }


def _cached_project_p4_status(p4_user, p4_client):
    """Return Project status dict from session cache, or None if a p4 query is needed."""
    _cached_key = _cache.get('connection_report_key')
    _cached = _cache.get('connection_report')
    if _cached and _cached_key:
        if _cached_key[0] == p4_user and _cached_key[1] == p4_client:
            return _project_status_from_report(_cached)
        if _cached.get('p4User') == p4_user and _cached.get('p4Client') == p4_client:
            return _project_status_from_report(_cached)
    return _project_status_from_info_cache(p4_user, p4_client)


def _parse_tag_block(lines):
    """Parse one -ztag record (... key value lines) into a dict."""
    _out = {}
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).strip()
        if not _line.startswith('...'):
            continue
        _rest = _line[3:].strip()
        if not _rest:
            continue
        _sp = _rest.split(None, 1)
        if len(_sp) == 1:
            _key, _val = _sp[0], True
        else:
            _key, _val = _sp[0], _sp[1]
        if _key in _out:
            _existing = _out[_key]
            if isinstance(_existing, list):
                _existing.append(_val)
            else:
                _out[_key] = [_existing, _val]
        else:
            _out[_key] = _val
    return _out


def _parse_tag_records(lines):
    """Parse -ztag output with multiple records separated by blank lines."""
    _records = []
    _block = []
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).rstrip('\r\n')
        if not _line.strip() or _line.strip().startswith('exit:'):
            if _block:
                _rec = _parse_tag_block(_block)
                if _rec:
                    _records.append(_rec)
                _block = []
            continue
        if _line.strip().lower().startswith('error:'):
            continue
        _block.append(_line)
    if _block:
        _rec = _parse_tag_block(_block)
        if _rec:
            _records.append(_rec)
    return _records


def _parse_colon_dict(lines):
    """Parse p4 info -s colon output (fallback)."""
    _out = {}
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).strip()
        if not _line or _line.startswith('exit:') or _line.lower().startswith('error:'):
            continue
        if ':' not in _line:
            continue
        _key, _val = _line.split(':', 1)
        _key = _key.strip()
        _val = _val.strip()
        _parts = _key.split()
        _camel = _parts[0].lower() + ''.join(_p.capitalize() for _p in _parts[1:])
        _out[_camel] = _val
    return _out


def _normalize_error(msg):
    if not msg:
        return msg
    _m = str(msg).strip()
    if _m.lower().startswith('error:'):
        return _m[6:].strip()
    return _m


def _coerce_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tag_values(tag, key):
    _val = (tag or {}).get(key)
    if _val is None:
        return []
    if isinstance(_val, list):
        return _val
    return [_val]


def _derive_file_status(out, tag=None):
    """Add inClient / checkout / sync / lock flags and human-readable summary."""
    tag = tag or {}

    if out.get('notInClient'):
        out['inClient'] = False
        out['checkedOut'] = False
        out['outOfDate'] = False
        out['synced'] = False
        out['lockedByOther'] = False
        out['statusLabels'] = ['not in client view']
        out['statusSummary'] = 'not in client view'
        return out

    out['inClient'] = True

    if out.get('notOnDepot') and not tag:
        out['checkedOut'] = False
        out['outOfDate'] = False
        out['synced'] = False
        out['lockedByOther'] = False
        out['statusLabels'] = ['in client view', 'not on depot']
        out['statusSummary'] = 'in client view, not on depot'
        return out

    _head_rev = _coerce_int(tag.get('headRev'))
    _have_rev = _coerce_int(tag.get('haveRev'))
    out['headRev'] = _head_rev
    out['haveRev'] = _have_rev
    out['depotFile'] = tag.get('depotFile')
    out['clientFile'] = tag.get('clientFile')
    out['headAction'] = tag.get('headAction')
    out['fileType'] = tag.get('type')

    _action = tag.get('action')
    out['openAction'] = _action
    out['change'] = tag.get('change')
    out['checkedOut'] = bool(_action)

    _other_opens = _tag_values(tag, 'otherOpen')
    _other_locks = _tag_values(tag, 'otherLock')
    out['otherOpen'] = _other_opens or None
    out['otherLock'] = _other_locks or None
    out['ourLock'] = tag.get('ourLock')
    out['lockedByOther'] = bool(_other_locks or _other_opens)

    if _head_rev is not None and _have_rev is not None:
        out['synced'] = _head_rev == _have_rev
        out['outOfDate'] = _have_rev < _head_rev
    else:
        out['synced'] = None
        out['outOfDate'] = None

    if out.get('checkedOut'):
        out['synced'] = True

    _labels = ['in client view']
    if out.get('onDepot'):
        _labels.append('on depot')
    else:
        _labels.append('not on depot')

    if out.get('checkedOut'):
        _labels.append('checked out ({0})'.format(_action))
        if out.get('change') and str(out['change']).lower() != 'default':
            _labels.append('change {0}'.format(out['change']))
    elif out.get('outOfDate'):
        _labels.append('out of date (have {0}, head {1})'.format(_have_rev, _head_rev))
    elif out.get('synced'):
        _labels.append('synced')
    else:
        _labels.append('not opened')

    if _other_locks:
        _labels.append('locked by {0}'.format(', '.join(_other_locks)))
    elif _other_opens:
        _labels.append('open elsewhere ({0})'.format(', '.join(_other_opens)))

    out['statusLabels'] = _labels
    out['statusSummary'] = ', '.join(_labels)
    return out


def format_file_status(file_dat):
    """One-line summary for UI / logs."""
    if not file_dat:
        return '(none)'
    _path = file_dat.get('path', '?')
    if file_dat.get('error'):
        return '{0} — error: {1}'.format(_path, file_dat['error'])
    if file_dat.get('statusSummary'):
        return '{0} — {1}'.format(_path, file_dat['statusSummary'])
    if file_dat.get('notInClient'):
        return '{0} — not in client view'.format(_path)
    if file_dat.get('notOnDepot'):
        return '{0} — not on depot'.format(_path)
    return _path


def _p4run(*args, **kwargs):
    """
    Run p4 subprocess with explicit -u / -c (required for server commands).

    :keyword p4_user: Perforce username
    :keyword p4_client: Perforce client workspace name
    :keyword ztag: Pass -ztag (default True for server queries)
    :keyword use_s: Pass -s instead of -ztag (e.g. p4 set)
    :returns: dict ok, lines, stderr, exitCode, tagRecords, tag
    """
    _p4_user = kwargs.pop('p4_user', None)
    _p4_client = kwargs.pop('p4_client', None)
    _ztag = kwargs.pop('ztag', True)
    _use_s = kwargs.pop('use_s', False)
    _cwd = kwargs.pop('cwd', None)

    _cmd = ['p4']
    if _p4_user:
        _cmd.extend(['-u', str(_p4_user)])
    if _p4_client:
        _cmd.extend(['-c', str(_p4_client)])
    if _use_s:
        _cmd.append('-s')
    elif _ztag:
        _cmd.append('-ztag')
    _cmd.extend([str(a) for a in args])

    try:
        _proc = subprocess.Popen(
            _cmd,
            cwd=_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **_P4_SUBPROCESS_KW,
        )
    except FileNotFoundError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': 'p4 executable not found',
            'exitCode': -1,
            'tag': {},
            'tagRecords': [],
            'error': str(err),
        }
    except OSError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': str(err),
            'exitCode': -1,
            'tag': {},
            'tagRecords': [],
            'error': str(err),
        }

    _stdout, _stderr = _proc.communicate()
    _exit = _proc.returncode

    try:
        _text = _stdout.decode('utf-8', errors='replace')
    except Exception:
        _text = _stdout.decode('latin-1', errors='replace')

    _lines = [_strip_info_prefix(l) for l in _text.splitlines()]
    _err = _stderr.decode('utf-8', errors='replace').strip()
    if not _err:
        _err_lines = [l for l in _lines if l.lower().startswith('error:')]
        if _err_lines:
            _err = _err_lines[0]

    _tag = _parse_tag_block(_lines)
    _tag_records = _parse_tag_records(_lines)
    _errors = [l for l in _lines if l.lower().startswith('error:')]
    _ok = _exit == 0 and not _errors

    return {
        'ok': _ok,
        'lines': _lines,
        'stderr': _normalize_error(_err),
        'exitCode': _exit,
        'tag': _tag,
        'tagRecords': _tag_records,
    }


def _require_connection(p4_user=None, p4_client=None):
    _user, _client = resolve_connection(p4_user, p4_client)
    if not _user or not _client:
        return None, None, 'p4_user and p4_client required (pass args or set CGM_P4USER/CGM_P4CLIENT)'
    return _user, _client, None


def _scene_path_get(scene_path=None):
    if scene_path:
        return os.path.normpath(scene_path)
    try:
        import maya.cmds as mc
        _scene = mc.file(q=True, sn=True)
        if _scene:
            return os.path.normpath(_scene)
    except Exception:
        pass
    return None


#>>> Public API — connectivity
#===================================================================
def is_available(force=False, p4_user=None, p4_client=None):
    """Return True when p4 info succeeds with explicit user and client."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _cache['available'] = False
        _cache['info'] = None
        return False

    if not force and _cache.get('available') is not None:
        if _cache.get('p4_user') == _user and _cache.get('p4_client') == _client:
            return _cache['available']

    _res = _p4run('info', p4_user=_user, p4_client=_client, ztag=True)
    _cache['p4_user'] = _user
    _cache['p4_client'] = _client
    _cache['available'] = bool(_res['ok'])
    if _res['ok']:
        _info = dict(_res['tag'])
        if not _info:
            _info = _parse_colon_dict(_res['lines'])
        _cache['info'] = _info
    else:
        _cache['info'] = None
    return _cache['available']


def query_project_p4_status(p4_user=None, p4_client=None, force=False):
    """
    Lightweight Perforce status for Project UI (no logging).

    Returns dict: connected (bool), label (str), reason (optional).
    """
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err or not _user or not _client:
        return {
            'connected': False,
            'label': 'P4: not connected — set user/client in cgmP4',
            'reason': _err or 'missing credentials',
        }

    if not force:
        _cached_status = _cached_project_p4_status(_user, _client)
        if _cached_status is not None:
            log.info('Using cached Perforce status (project)')
            return _cached_status

    log.info('Getting Perforce status (project)...')
    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {
            'connected': False,
            'label': 'P4: not connected — p4 info failed',
            'reason': 'p4 info failed',
        }

    _info = connection_info(force=force, p4_user=_user, p4_client=_client)
    if not _info.get('connected'):
        _reason = _info.get('reason') or 'unknown'
        return {
            'connected': False,
            'label': 'P4: not connected — {0}'.format(_reason),
            'reason': _reason,
        }

    _uname = _info.get('userName') or _user
    _cname = _info.get('clientName') or _client
    return {
        'connected': True,
        'label': 'P4: {0} @ {1}'.format(_uname, _cname),
        'connection': _info,
    }


def connection_info(force=False, p4_user=None, p4_client=None):
    """Parsed p4 info for explicit user/client (-u / -c / -ztag info)."""
    if force:
        _clear_cache()

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {
            'connected': False,
            'reason': _err,
            'p4User': _user,
            'p4Client': _client,
        }

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        _res = _p4run('info', p4_user=_user, p4_client=_client, ztag=True)
        return {
            'connected': False,
            'reason': _res.get('stderr') or 'p4 info failed',
            'p4User': _user,
            'p4Client': _client,
        }

    _info = dict(_cache.get('info') or {})
    _info['connected'] = True
    _info['p4User'] = _user
    _info['p4Client'] = _client
    return _normalize_connection_info(_info, p4_user=_user, p4_client=_client)


def _info_get_str(tag, *keys):
    for _key in keys:
        _val = (tag or {}).get(_key)
        if _val is None or _val is True:
            continue
        _s = str(_val).strip()
        if _s:
            return _s
    return None


def _normalize_connection_info(info, p4_user=None, p4_client=None):
    """Resolve clientRoot/stream with ztag key fallbacks and p4 client -o if needed."""
    _info = dict(info or {})
    _root = _info_get_str(_info, 'clientRoot', 'ClientRoot', 'root', 'Root')
    _stream = _info_get_str(_info, 'clientStream', 'stream', 'Stream', 'clientStream')

    if not _root and p4_user and p4_client:
        _res = _p4run('client', '-o', p4_client, p4_user=p4_user, p4_client=p4_client, ztag=True)
        _root = _info_get_str(_res.get('tag') or {}, 'Root', 'root')

    _info['clientRoot'] = _root or ''
    if _stream:
        _info['clientStream'] = _stream
    return _info


def query_opened(p4_user=None, p4_client=None, force=False):
    """
    Opened files grouped by changelist (p4 -u -c -ztag opened).
    """
    _empty = {'default': [], 'changes': {}, 'total': 0, 'rawCount': 0}
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return dict(_empty, error=_err)

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return dict(_empty, error='p4 info failed')

    _res = _p4run('opened', p4_user=_user, p4_client=_client, ztag=True)
    if not _res['ok']:
        return dict(_empty, error=_res.get('stderr') or 'p4 opened failed')

    _default = []
    _changes = {}
    _count = 0

    for _rec in _res.get('tagRecords') or []:
        if not _rec.get('depotFile'):
            continue
        _count += 1
        _change_raw = str(_rec.get('change', 'default'))
        _rev = _rec.get('rev')
        try:
            _rev = int(_rev)
        except (TypeError, ValueError):
            pass
        _entry = {
            'depotFile': _rec.get('depotFile'),
            'clientFile': _rec.get('clientFile'),
            'rev': _rev,
            'action': _rec.get('action'),
            'change': _change_raw,
            'type': _rec.get('type'),
        }
        if _change_raw.lower() == 'default':
            _default.append(_entry)
        else:
            try:
                _cl = int(_change_raw)
            except ValueError:
                _cl = _change_raw
            _changes.setdefault(_cl, []).append(_entry)

    return {
        'default': _default,
        'changes': _changes,
        'total': _count,
        'rawCount': _count,
    }


def query_pending_changes(p4_user=None, p4_client=None, force=False):
    """Pending changelists for user/client."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'error': _err, 'changes': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'error': 'p4 info failed', 'changes': []}

    _res = _p4run(
        'changes', '-s', 'pending', '-u', _user, '-c', _client,
        p4_user=_user, p4_client=_client, ztag=False, use_s=True,
    )
    if not _res['ok']:
        return {'error': _res.get('stderr') or 'p4 changes failed', 'changes': []}

    _changes = []
    for _line in _res['lines']:
        _line = _line.strip()
        if not _line or _line.lower().startswith('error:'):
            continue
        _m = _CHANGE_LINE_RE.match(_line)
        if not _m:
            continue
        _changes.append({
            'change': int(_m.group('change')),
            'status': _m.group('status'),
            'line': _line,
        })

    return {'changes': _changes}


def query_file_status(disk_path, p4_user=None, p4_client=None, force=False):
    """
    Workspace membership and depot status for a disk path (p4 -u -c -ztag fstat).

    Returns dict including:
      inClient, onDepot, checkedOut, outOfDate, synced, lockedByOther,
      statusLabels, statusSummary, headRev, haveRev, openAction, otherOpen, ...
    """
    _norm = os.path.normpath(disk_path) if disk_path else disk_path
    _out = {
        'path': _norm,
        'inClient': None,
        'onDepot': False,
        'notInClient': False,
        'notOnDepot': False,
        'checkedOut': False,
        'outOfDate': False,
        'synced': None,
        'lockedByOther': False,
        'openAction': None,
        'change': None,
        'headRev': None,
        'haveRev': None,
        'otherOpen': None,
        'otherLock': None,
        'ourLock': None,
        'headAction': None,
        'depotFile': None,
        'clientFile': None,
        'fileType': None,
        'statusLabels': [],
        'statusSummary': '',
    }

    if not _norm:
        _out['error'] = 'path is empty'
        return _out

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _out['error'] = _err
        return _out

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        _out['error'] = 'p4 info failed'
        return _out

    _res = _p4run('fstat', _norm, p4_user=_user, p4_client=_client, ztag=True)
    _tag = _res.get('tag') or {}

    if _tag:
        _out['onDepot'] = True
        if _tag.get('headAction') == 'delete':
            _out['onDepot'] = False
            _out['notOnDepot'] = True
        return _derive_file_status(_out, _tag)

    _err_text = ' '.join(_res['lines'] + [_res.get('stderr') or '']).lower()
    if 'not in client view' in _err_text or 'not under' in _err_text:
        _out['notInClient'] = True
        return _derive_file_status(_out)
    if 'no such file' in _err_text or 'not on depot' in _err_text or 'not in depot' in _err_text:
        _out['notOnDepot'] = True
        return _derive_file_status(_out)

    if not _res['ok']:
        _out['error'] = _res.get('stderr') or 'p4 fstat failed'
    return _out


def _new_file_status_out(disk_path):
    """Base dict for query_file_status / query_files_status."""
    _norm = _normalize_disk_path(disk_path) if disk_path else disk_path
    return {
        'path': _norm,
        'inClient': None,
        'onDepot': False,
        'notInClient': False,
        'notOnDepot': False,
        'checkedOut': False,
        'outOfDate': False,
        'synced': None,
        'lockedByOther': False,
        'openAction': None,
        'change': None,
        'headRev': None,
        'haveRev': None,
        'otherOpen': None,
        'otherLock': None,
        'ourLock': None,
        'headAction': None,
        'depotFile': None,
        'clientFile': None,
        'fileType': None,
        'statusLabels': [],
        'statusSummary': '',
    }


def _file_status_from_fstat_tag(disk_path, tag):
    """Build full status dict from one fstat ztag record."""
    _out = _new_file_status_out(disk_path)
    if not tag:
        return _out
    _out['onDepot'] = True
    if tag.get('headAction') == 'delete':
        _out['onDepot'] = False
        _out['notOnDepot'] = True
    return _derive_file_status(_out, tag)


def _path_lookup_key(disk_path):
    """Case-insensitive normpath key for batch fstat result matching."""
    _norm = _normalize_disk_path(disk_path)
    if not _norm:
        return None
    return os.path.normcase(_norm)


def _fstat_missing_path_status(disk_path, res):
    """Classify a path absent from batch fstat tagRecords (per-path error lines)."""
    _norm = _normalize_disk_path(disk_path)
    _err_text = ' '.join((res.get('lines') or []) + [res.get('stderr') or '']).lower()
    _path_bits = [_norm.lower() if _norm else '']
    if _norm:
        _path_bits.append(os.path.basename(_norm).lower())
    _matched = False
    for _raw in res.get('lines') or []:
        _line = _strip_info_prefix(_raw).lower()
        if not any(_b and _b in _line for _b in _path_bits if _b):
            continue
        _matched = True
        if 'not in client view' in _line or 'not under' in _line:
            _out = _new_file_status_out(disk_path)
            _out['notInClient'] = True
            return _derive_file_status(_out)
        if 'no such file' in _line or 'not on depot' in _line or 'not in depot' in _line:
            _out = _new_file_status_out(disk_path)
            _out['notOnDepot'] = True
            return _derive_file_status(_out)
    if _matched or not res.get('ok'):
        _out = _new_file_status_out(disk_path)
        if not res.get('ok') and not _matched:
            _out['error'] = res.get('stderr') or 'p4 fstat failed'
        else:
            _out['notOnDepot'] = True
        return _derive_file_status(_out)
    _out = _new_file_status_out(disk_path)
    _out['notOnDepot'] = True
    return _derive_file_status(_out)


def classify_file_status_ui(file_dat):
    """
    Map query_file_status dict to Scene browser UI color key, or None for default file tint.

    Returns: 'locked_by_other' | 'checked_out' | 'marked_for_add' | 'out_of_sync' | 'unknown' | None
    """
    if not file_dat:
        return None
    if file_dat.get('error') and not file_dat.get('notInClient') and not file_dat.get('notOnDepot'):
        return None
    if file_dat.get('notInClient'):
        return None
    if file_dat.get('lockedByOther'):
        return 'locked_by_other'
    if file_dat.get('checkedOut'):
        if str(file_dat.get('openAction') or '').lower() == 'add':
            return 'marked_for_add'
        return 'checked_out'
    if file_dat.get('outOfDate'):
        return 'out_of_sync'
    if file_dat.get('notOnDepot') and file_dat.get('inClient'):
        return 'unknown'
    return None


def file_status_ui_suffix(file_dat, status_key):
    """Display-only parenthetical for Scene scroll alias, e.g. '(locked-by-other)'."""
    if not status_key:
        return None
    if status_key == 'locked_by_other':
        if file_dat and file_dat.get('otherLock'):
            return '(locked-by-other)'
        if file_dat and file_dat.get('otherOpen'):
            return '(open-elsewhere)'
        return '(locked-by-other)'
    _d = {
        'checked_out': '(checked-out)',
        'marked_for_add': '(marked-for-add)',
        'out_of_sync': '(out-of-sync)',
        'unknown': '(unknown)',
    }
    return _d.get(status_key)


def query_files_status(disk_paths, p4_user=None, p4_client=None, force=False):
    """
    Batch workspace / depot status for disk paths (single p4 -u -c -ztag fstat call).

    Returns dict normpath -> status dict (same shape as query_file_status).
    """
    _paths = []
    _seen = set()
    for _p in disk_paths or []:
        _norm = _normalize_disk_path(_p)
        if not _norm:
            continue
        _key = _path_lookup_key(_norm)
        if _key in _seen:
            continue
        _seen.add(_key)
        _paths.append(_norm)

    if not _paths:
        return {}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {_norm: dict(_new_file_status_out(_norm), error=_err) for _norm in _paths}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {
            _norm: dict(_new_file_status_out(_norm), error='p4 info failed')
            for _norm in _paths
        }

    _res = _p4run('fstat', *_paths, p4_user=_user, p4_client=_client, ztag=True)
    _by_key = {}
    for _rec in _res.get('tagRecords') or []:
        _client_file = _rec.get('clientFile')
        _lookup = _path_lookup_key(_client_file) if _client_file else None
        if not _lookup:
            continue
        _by_key[_lookup] = _file_status_from_fstat_tag(_client_file, _rec)

    _out = {}
    for _norm in _paths:
        _lookup = _path_lookup_key(_norm)
        if _lookup in _by_key:
            _dat = dict(_by_key[_lookup])
            _dat['path'] = _norm
            _out[_norm] = _dat
        else:
            _out[_norm] = _fstat_missing_path_status(_norm, _res)
    return _out


def is_under_client(disk_path, p4_user=None, p4_client=None, force=False):
    """True when disk_path is mapped in the current p4 client workspace."""
    _dat = query_file_status(disk_path, p4_user=p4_user, p4_client=p4_client, force=force)
    if _dat.get('error') and not _dat.get('notInClient'):
        return False
    return bool(_dat.get('inClient'))


def query_path(disk_path, p4_user=None, p4_client=None, force=False):
    """Alias for query_file_status — workspace check + file status in one call."""
    return query_file_status(disk_path, p4_user=p4_user, p4_client=p4_client, force=force)


def query_path_report(disk_path, p4_user=None, p4_client=None, force=False):
    """Log path workspace/status summary; returns structured dict."""
    _str_func = 'query_path_report'
    _dat = query_file_status(disk_path, p4_user=p4_user, p4_client=p4_client, force=force)
    log.info(cgmGEN.logString_sub(_str_func, 'Path status'))
    log.info(format_file_status(_dat))
    if _dat.get('depotFile'):
        log.info('depotFile: {0}'.format(_dat.get('depotFile')))
    if _dat.get('clientFile'):
        log.info('clientFile: {0}'.format(_dat.get('clientFile')))
    if _dat.get('headRev') is not None:
        log.info('headRev: {0} | haveRev: {1}'.format(_dat.get('headRev'), _dat.get('haveRev')))
    if _dat.get('checkedOut'):
        log.info('open: {0} change {1}'.format(_dat.get('openAction'), _dat.get('change')))
    if _dat.get('lockedByOther'):
        if _dat.get('otherLock'):
            log.info('otherLock: {0}'.format(_dat.get('otherLock')))
        if _dat.get('otherOpen'):
            log.info('otherOpen: {0}'.format(_dat.get('otherOpen')))
    return _dat


#>>> Public API — write actions (UI / export prep)
#===================================================================
def _write_result(action, path, res):
    return {
        'ok': bool(res.get('ok')),
        'action': action,
        'path': path,
        'stderr': res.get('stderr') or '',
        'lines': res.get('lines') or [],
    }


def _normalize_disk_path(disk_path):
    if not disk_path:
        return None
    return os.path.normpath(str(disk_path))


def _change_sort_key(change_id):
    try:
        return (0, int(change_id))
    except (TypeError, ValueError):
        return (1, str(change_id))


def iter_opened_changelist_groups(opened_dat):
    """
    Display-order changelist groups from query_opened dict.

    Returns list of dicts: change, label, entries.
    """
    if not opened_dat or opened_dat.get('error'):
        return []

    _groups = []
    _default = opened_dat.get('default') or []
    if _default:
        _entries = [dict(_rec) for _rec in _default]
        _groups.append({
            'change': 'default',
            'label': 'Default ({0})'.format(len(_entries)),
            'entries': _entries,
        })

    for _cl in sorted((opened_dat.get('changes') or {}).keys(), key=_change_sort_key):
        _entries = [dict(_rec) for _rec in opened_dat['changes'][_cl]]
        _groups.append({
            'change': _cl,
            'label': 'Change {0} ({1})'.format(_cl, len(_entries)),
            'entries': _entries,
        })
    return _groups


def flatten_opened_entries(opened_dat):
    """Flatten query_opened dict into a single list of file entry dicts."""
    _entries = []
    for _grp in iter_opened_changelist_groups(opened_dat):
        _entries.extend(_grp['entries'])
    return _entries


def count_opened_in_change(opened_dat, change):
    """Count opened files sharing a changelist id (includes default)."""
    _target = str(change).lower()
    return sum(
        1 for _e in flatten_opened_entries(opened_dat)
        if str(_e.get('change', 'default')).lower() == _target
    )


def edit(disk_path, p4_user=None, p4_client=None, changelist=None, force=False):
    """p4 edit — open depot file for edit."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'edit', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'edit', 'path': _path, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'edit', 'path': _path, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['edit']
    if changelist is not None:
        _args.extend(['-c', str(changelist)])
    _args.append(_path)

    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()
    return _write_result('edit', _path, _res)


def add(disk_path, p4_user=None, p4_client=None, file_type=None, changelist=None, force=False):
    """p4 add — add new local file to depot."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'add', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'add', 'path': _path, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'add', 'path': _path, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['add']
    if file_type:
        _args.extend(['-t', str(file_type)])
    elif _path.lower().endswith('.fbx'):
        _args.extend(['-t', 'binary'])
    if changelist is not None:
        _args.extend(['-c', str(changelist)])
    _args.append(_path)

    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()
    return _write_result('add', _path, _res)


def edit_or_add(disk_path, p4_user=None, p4_client=None, file_type=None, changelist=None, force=False):
    """p4 edit if on depot, else p4 add for in-client local files."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'edit_or_add', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _stat = query_file_status(_path, p4_user=p4_user, p4_client=p4_client, force=force)
    if _stat.get('error') and not _stat.get('notInClient') and not _stat.get('notOnDepot'):
        return {'ok': False, 'action': 'edit_or_add', 'path': _path, 'stderr': _stat.get('error'), 'lines': []}
    if _stat.get('notInClient'):
        return {
            'ok': False, 'action': 'edit_or_add', 'path': _path,
            'stderr': 'path not in client view', 'lines': [],
        }
    if _stat.get('lockedByOther'):
        return {
            'ok': False, 'action': 'edit_or_add', 'path': _path,
            'stderr': 'file locked or open elsewhere: {0}'.format(
                _stat.get('otherLock') or _stat.get('otherOpen')),
            'lines': [],
        }
    if _stat.get('checkedOut'):
        return {'ok': True, 'action': _stat.get('openAction') or 'edit', 'path': _path, 'stderr': '', 'lines': []}

    if _stat.get('onDepot'):
        return edit(_path, p4_user=p4_user, p4_client=p4_client, changelist=changelist, force=force)
    return add(
        _path, p4_user=p4_user, p4_client=p4_client, file_type=file_type,
        changelist=changelist, force=force,
    )


def revert(disk_path, p4_user=None, p4_client=None, force=False):
    """p4 revert — discard local open on file."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'revert', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'revert', 'path': _path, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'revert', 'path': _path, 'stderr': 'p4 info failed', 'lines': []}

    _res = _p4run('revert', _path, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()
    return _write_result('revert', _path, _res)


def revert_change(change, p4_user=None, p4_client=None, force=False):
    """p4 revert -c — revert all opened files in a changelist."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'revert', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'revert', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    _cl_arg = 'default' if _change_str in ('default', '') else str(change)

    _res = _p4run('revert', '-c', _cl_arg, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'revert',
        'change': change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def sync_file(disk_path, force=False, p4_user=None, p4_client=None):
    """p4 sync — update one disk path to head revision."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'sync', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'sync', 'path': _path, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'sync', 'path': _path, 'stderr': 'p4 info failed', 'lines': []}

    if force:
        _res = _p4run('sync', '-f', _path, p4_user=_user, p4_client=_client, ztag=False)
    else:
        _res = _p4run('sync', _path, p4_user=_user, p4_client=_client, ztag=False)

    if _res.get('ok'):
        _clear_cache()

    _out = _write_result('sync', _path, _res)
    _out['path'] = _path
    return _out


def sync_workspace(force=False, p4_user=None, p4_client=None):
    """p4 sync — update entire client workspace to head."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'sync', 'stderr': _err, 'lines': []}

    if not is_available(force=True, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'sync', 'stderr': 'p4 info failed', 'lines': []}

    _info = connection_info(force=False, p4_user=_user, p4_client=_client)
    _root = _info.get('clientRoot')
    if _root:
        _target = os.path.normpath(_root)
        if not _target.endswith('...'):
            _target = os.path.join(_target, '...')
    else:
        _target = '...'

    if force:
        _res = _p4run('sync', '-f', _target, p4_user=_user, p4_client=_client, ztag=False)
    else:
        _res = _p4run('sync', _target, p4_user=_user, p4_client=_client, ztag=False)

    if _res.get('ok'):
        _clear_cache()

    return {
        'ok': bool(_res.get('ok')),
        'action': 'sync',
        'target': _target,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def submit_change(change, description=None, p4_user=None, p4_client=None, force=False):
    """p4 submit — submit pending changelist (or default when change is 'default')."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        _args = ['submit']
    else:
        _args = ['submit', '-c', str(change)]

    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()

    return {
        'ok': bool(_res.get('ok')),
        'action': 'submit',
        'change': change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def submit_paths(paths, change=None, p4_user=None, p4_client=None, force=False):
    """p4 submit — submit specific opened files (optionally scoped to a changelist)."""
    _paths = []
    for _raw in paths or []:
        _path = _normalize_disk_path(_raw) or str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'no paths', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        _args = ['submit'] + _paths
    else:
        _args = ['submit', '-c', str(change)] + _paths

    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _clear_cache()

    return {
        'ok': bool(_res.get('ok')),
        'action': 'submit',
        'change': change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def query_connection(scene_path=None, force=False, p4_user=None, p4_client=None, expected_user=None):
    """
    Compose connectivity, opened files, pending changelists, and scene fstat.

    expected_user: deprecated alias for p4_user when p4_user omitted.
    Session cache keyed by (user, client, scene_path) unless force=True.
    """
    if p4_user is None and expected_user:
        p4_user = expected_user

    _scene = _scene_path_get(scene_path)
    _user, _client, _err = _require_connection(p4_user, p4_client)
    _key = _connection_report_cache_key(_user, _client, _scene)

    if not force:
        _cached = _get_cached_connection_report(_key)
        if _cached is not None:
            log.info('Using cached Perforce status')
            return _cached

    log.info('Getting Perforce status...')
    _info = connection_info(force=force, p4_user=_user, p4_client=_client)

    _report = {
        'connected': bool(_info.get('connected')),
        'connection': _info,
        'p4User': _user,
        'p4Client': _client,
        'opened': None,
        'pendingChanges': None,
        'scene': None,
    }

    if _err:
        _report['reason'] = _err
        _set_cached_connection_report(_key, _report)
        return dict(_report)

    if not _report['connected']:
        _report['reason'] = _info.get('reason')
        _set_cached_connection_report(_key, _report)
        return dict(_report)

    _report['opened'] = query_opened(p4_user=_user, p4_client=_client, force=force)
    _report['pendingChanges'] = query_pending_changes(p4_user=_user, p4_client=_client, force=force)

    if _scene:
        _report['scene'] = query_file_status(_scene, p4_user=_user, p4_client=_client, force=force)
    else:
        _report['scene'] = {'skipped': True, 'reason': 'scene not saved'}

    _set_cached_connection_report(_key, _report)
    return dict(_report)


def _format_scene_status(scene_dat):
    if not scene_dat:
        return 'scene: (none)'
    if scene_dat.get('skipped'):
        return 'scene: {0}'.format(scene_dat.get('reason', 'skipped'))
    return 'scene: {0}'.format(format_file_status(scene_dat))


def log_status_report(dat):
    """
    Log a human-readable P4 report from a structured dict (no p4 queries).

    Use after query_connection() or from a UI buffer populated by Refresh.
    """
    _str_func = 'query_status_report'
    _dat = dat or {}
    _conn = _dat.get('connection') or {}

    log.info(cgmGEN.logString_sub(_str_func, 'P4 Connection'))
    log.info('p4_user: {0}'.format(_dat.get('p4User') or '(not set)'))
    log.info('p4_client: {0}'.format(_dat.get('p4Client') or '(not set)'))
    log.info('connected: {0}'.format(_dat.get('connected')))

    if not _dat.get('connected'):
        log.info('reason: {0}'.format(_dat.get('reason') or _conn.get('reason')))
        return _dat

    log.info('user (p4 info): {0}'.format(_conn.get('userName')))
    log.info('client: {0}'.format(_conn.get('clientName')))
    log.info('clientRoot: {0}'.format(_conn.get('clientRoot')))
    log.info('server: {0}'.format(_conn.get('serverAddress')))
    log.info('serverVersion: {0}'.format(_conn.get('serverVersion')))
    if _conn.get('stream'):
        log.info('stream: {0}'.format(_conn.get('stream')))
    elif _conn.get('clientStream'):
        log.info('stream: {0}'.format(_conn.get('clientStream')))

    _opened = _dat.get('opened') or {}
    if _opened.get('error'):
        log.info(cgmGEN.logString_sub(_str_func, 'Opened files'))
        log.info(_opened['error'])
    else:
        _total = _opened.get('total', 0)
        log.info(cgmGEN.logString_sub(_str_func, 'Opened files ({0})'.format(_total)))
        _default = _opened.get('default') or []
        if _default:
            log.info('[default] {0} file(s)'.format(len(_default)))
            for _rec in _default:
                log.info('  {0} {1}#{2}'.format(_rec['action'], _rec['depotFile'], _rec['rev']))
        for _cl in sorted((_opened.get('changes') or {}).keys(), key=lambda x: int(x) if str(x).isdigit() else x):
            _files = _opened['changes'][_cl]
            log.info('[change {0}] {1} file(s)'.format(_cl, len(_files)))
            for _rec in _files:
                log.info('  {0} {1}#{2}'.format(_rec['action'], _rec['depotFile'], _rec['rev']))

    _pending = _dat.get('pendingChanges') or {}
    log.info(cgmGEN.logString_sub(_str_func, 'Pending changelists'))
    if _pending.get('error'):
        log.info(_pending['error'])
    elif not (_pending.get('changes') or []):
        log.info('(none)')
    else:
        for _ch in _pending['changes']:
            log.info('{0} *{1}*'.format(_ch.get('change'), _ch.get('status')))

    log.info(cgmGEN.logString_sub(_str_func, 'Scene file'))
    log.info(_format_scene_status(_dat.get('scene')))

    return _dat


def query_status_report(
    p4_user=None,
    p4_client=None,
    scene_path=None,
    force=False,
    expected_user=None,
):
    """
    Log a human-readable P4 connectivity report and return the structured dict.

    Script Editor:
        import cgm.core.lib.perforce as P4UTIL
        P4UTIL.query_status_report(
            p4_user='josh.burton',
            p4_client='josh.burton_WX-MXL6062Q6F_5734_SourceArt-DDE',
        )
    """
    if p4_user is None and expected_user:
        p4_user = expected_user

    _dat = query_connection(
        scene_path=scene_path,
        force=force,
        p4_user=p4_user,
        p4_client=p4_client,
    )
    log_status_report(_dat)
    return _dat
