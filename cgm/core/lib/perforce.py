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

# p4 changes (text): Change 12345 on YYYY/MM/DD by user@client *pending* 'description'
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
    """Persist p4 user/client to Maya optionVars.

    Clears the P4 session cache only when user or client actually changes.
    """
    import cgm.core.cgm_Meta as cgmMeta
    _prev_user, _prev_client = get_connection_prefs()
    _changed = False

    if p4_user is not None:
        _new_user = str(p4_user).strip()
        if _new_user != (_prev_user or ''):
            _changed = True
        cgmMeta.cgmOptionVar(OPT_P4_USER, varType='string', defaultValue='').setValue(_new_user)
    if p4_client is not None:
        _new_client = str(p4_client).strip()
        if _new_client != (_prev_client or ''):
            _changed = True
        cgmMeta.cgmOptionVar(OPT_P4_CLIENT, varType='string', defaultValue='').setValue(
            _new_client)
    if _changed:
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


FSTAT_QUERY_CHUNK = 96

DEFAULT_P4_CACHE_DIR_MASK = [
    'meta', '.mayaSwatches', 'incrementalSave', 'cgmDat', 'mayaSwatches',
]


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


def _collect_fstat_indexed_values(tag, prefix):
    """Collect prefixN ztag fields (e.g. otherOpen0) into index order."""
    _indexed = []
    _plen = len(prefix)
    for _key, _val in (tag or {}).items():
        if not isinstance(_key, str) or not _key.startswith(prefix):
            continue
        _suffix = _key[len(_plen):]
        if _suffix.isdigit():
            _indexed.append((int(_suffix), _val))
    if not _indexed:
        return []
    _indexed.sort(key=lambda item: item[0])
    return [v for _, v in _indexed]


def _fstat_other_count(tag, prefix):
    """Numeric otherOpen/otherLock count field from fstat (0 when absent)."""
    _max = 0
    for _val in _tag_values(tag, prefix):
        _n = _coerce_int(_val)
        if _n is not None and _n > _max:
            _max = _n
    return _max


def _fstat_other_user_values(tag, prefix):
    """
    User/workspace strings for otherOpen/otherLock.

    p4 -ztag fstat emits indexed keys (otherOpen0, otherLock0) plus optional
    count fields (otherOpen, otherLock). Match zooPy-style parsing.
    """
    _indexed = _collect_fstat_indexed_values(tag, prefix)
    if _indexed:
        return _indexed

    _users = []
    for _val in _tag_values(tag, prefix):
        if _val is None or _val is True:
            continue
        _s = str(_val).strip()
        if not _s or _s.isdigit():
            continue
        _users.append(_val)
    return _users


def _opened_entry_user_client(rec):
    """user@client string from a p4 opened ztag record."""
    _user = rec.get('user')
    _client = rec.get('client')
    if _user and _client:
        return '{0}@{1}'.format(_user, _client)
    return _user or _client


def _query_depot_opened_all(depot_files, p4_user=None, p4_client=None):
    """
    p4 opened -a on depot path(s) — all users/workspaces with the file open.

    Returns dict depotFile -> [opened ztag records].
    """
    _files = []
    _seen = set()
    for _f in depot_files or []:
        if not _f:
            continue
        _s = str(_f).strip()
        if not _s or _s in _seen:
            continue
        _seen.add(_s)
        _files.append(_s)
    if not _files:
        return {}

    _res = _p4run('opened', '-a', *_files, p4_user=p4_user, p4_client=p4_client, ztag=True)
    if not _res.get('ok'):
        return {}

    _by_depot = {}
    for _rec in _res.get('tagRecords') or []:
        _depot = _rec.get('depotFile')
        if not _depot:
            continue
        _by_depot.setdefault(_depot, []).append(_rec)
    return _by_depot


def _merge_depot_opens_into_status(file_dat, opened_recs, p4_user, p4_client):
    """Fill otherOpen / lockedByOther from p4 opened -a when fstat omitted them."""
    if not file_dat or not opened_recs:
        return file_dat

    _others = []
    _other_actions = []
    for _rec in opened_recs:
        _ou = _rec.get('user')
        _oc = _rec.get('client')
        if _ou == p4_user and _oc == p4_client:
            continue
        _uc = _opened_entry_user_client(_rec)
        if _uc:
            _others.append(_uc)
        _act = _rec.get('action')
        if _act:
            _other_actions.append(_act)

    if not _others:
        return file_dat

    _existing = file_dat.get('otherOpen') or []
    if isinstance(_existing, str):
        _existing = [_existing]
    _merged = []
    _seen = set()
    for _v in list(_existing) + _others:
        _s = str(_v)
        if _s in _seen:
            continue
        _seen.add(_s)
        _merged.append(_v)

    file_dat['otherOpen'] = _merged
    file_dat['otherOpenActions'] = _other_actions or None
    file_dat['lockedByOther'] = True
    _apply_other_open_to_status_labels(file_dat)
    return file_dat


def _apply_other_open_to_status_labels(file_dat):
    """Refresh statusLabels / statusSummary after otherOpen is set."""
    if not file_dat.get('lockedByOther'):
        return
    _labels = [
        _l for _l in (file_dat.get('statusLabels') or [])
        if not str(_l).startswith('open elsewhere')
        and not str(_l).startswith('locked by')]
    _locks = file_dat.get('otherLock') or []
    _opens = file_dat.get('otherOpen') or []
    if _locks:
        _labels.append('locked by {0}'.format(', '.join(str(x) for x in _locks)))
    elif _opens:
        _labels.append('open elsewhere ({0})'.format(', '.join(str(x) for x in _opens)))
    else:
        _labels.append('open elsewhere')
    file_dat['statusLabels'] = _labels
    file_dat['statusSummary'] = ', '.join(_labels)


def _enrich_status_with_depot_opens(status_by_path, p4_user, p4_client):
    """One p4 opened -a batch per fstat chunk — matches P4V Checked Out By."""
    if not status_by_path:
        return status_by_path

    _depot_files = []
    _depot_for_path = {}
    for _path, _dat in status_by_path.items():
        if not _dat or _dat.get('notInClient') or not _dat.get('onDepot'):
            continue
        if _dat.get('lockedByOther') and _dat.get('otherOpen'):
            continue
        _depot = _dat.get('depotFile')
        if not _depot:
            continue
        _depot_files.append(_depot)
        _depot_for_path[_path] = _depot

    if not _depot_files:
        return status_by_path

    _opened_by_depot = _query_depot_opened_all(_depot_files, p4_user=p4_user, p4_client=p4_client)
    if not _opened_by_depot:
        return status_by_path

    for _path, _depot in _depot_for_path.items():
        _recs = _opened_by_depot.get(_depot)
        if _recs:
            _merge_depot_opens_into_status(status_by_path[_path], _recs, p4_user, p4_client)
    return status_by_path


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

    _other_opens = _fstat_other_user_values(tag, 'otherOpen')
    _other_locks = _fstat_other_user_values(tag, 'otherLock')
    out['otherOpen'] = _other_opens or None
    out['otherLock'] = _other_locks or None
    out['ourLock'] = tag.get('ourLock')
    out['lockedByOther'] = bool(
        _other_locks
        or _other_opens
        or _fstat_other_count(tag, 'otherOpen') > 0
        or _fstat_other_count(tag, 'otherLock') > 0
        or _collect_fstat_indexed_values(tag, 'otherAction'))

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


def _p4run_input(*args, **kwargs):
    """
    Run p4 with stdin payload (e.g. p4 submit -i, p4 change -i).

    :keyword input_text: UTF-8 text piped to stdin
    :returns: same shape as _p4run
    """
    _input_text = kwargs.pop('input_text', None)
    _p4_user = kwargs.pop('p4_user', None)
    _p4_client = kwargs.pop('p4_client', None)
    _ztag = kwargs.pop('ztag', False)
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
            stdin=subprocess.PIPE,
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

    _input_bytes = None
    if _input_text is not None:
        _input_bytes = str(_input_text).encode('utf-8')

    _stdout, _stderr = _proc.communicate(input=_input_bytes)
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


def _change_spec_arg(change):
    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        return 'default'
    return str(change)


def _fetch_change_spec(change, p4_user=None, p4_client=None):
    """Return (spec_text, error). spec_text is None on failure."""
    _res = _p4run(
        'change', '-o', _change_spec_arg(change),
        p4_user=p4_user, p4_client=p4_client, ztag=False,
    )
    if not _res.get('ok'):
        return None, _res.get('stderr') or 'p4 change -o failed'
    return '\n'.join(_res.get('lines') or []), None


def _parse_change_spec_description(spec_text):
    """Extract Description body from a p4 change/submit form."""
    if not spec_text:
        return ''
    _desc_lines = []
    _in_desc = False
    for _line in spec_text.splitlines():
        if _line.startswith('Description:'):
            _in_desc = True
            _rest = _line[len('Description:'):].lstrip('\t ')
            if _rest:
                _desc_lines.append(_rest)
            continue
        if _in_desc:
            if _line.startswith('\t') or (_line.startswith(' ') and _line.strip()):
                _desc_lines.append(_line.lstrip('\t '))
                continue
            if _line.strip() == '':
                _desc_lines.append('')
                continue
            break
    return '\n'.join(_desc_lines).strip()


def _format_change_spec_description_lines(description):
    """Build Description: block lines for a p4 form."""
    _desc = (description or '').strip()
    _out = ['Description:']
    if not _desc:
        _out.append('\t<enter description here>')
        return _out
    for _line in _desc.splitlines():
        _out.append('\t' + _line)
    if len(_out) == 1:
        _out.append('\t' + _desc)
    return _out


def _depot_path_key(depot_path):
    """Normalize depot path for Files: line matching (strip #rev suffix)."""
    if not depot_path:
        return None
    return str(depot_path).split('#')[0].strip().lower()


def _build_opened_path_indexes(opened_dat):
    """Index p4 opened records by clientFile and depotFile lookup keys."""
    _by_client = {}
    _by_depot = {}
    _all = list(flatten_opened_entries(opened_dat or {}))
    for _entry in _all:
        _cf = _entry.get('clientFile')
        if _cf:
            _ck = _path_lookup_key(_cf)
            if _ck:
                _by_client[_ck] = _entry
        _dk = _depot_path_key(_entry.get('depotFile'))
        if _dk:
            _by_depot[_dk] = _entry
    return _by_client, _by_depot, _all


def _lookup_opened_entry(path, opened_by_client, opened_by_depot, all_entries=None):
    """Match a disk or depot path to an opened-file record."""
    _path_str = str(path).strip() if path else ''
    if not _path_str:
        return None
    if _path_str.startswith('//'):
        _hit = opened_by_depot.get(_depot_path_key(_path_str))
        if _hit:
            return _hit
    else:
        _ck = _path_lookup_key(_path_str)
        if _ck and _ck in opened_by_client:
            return opened_by_client[_ck]

    if not all_entries:
        return None

    _pk = _path_lookup_key(_path_str)
    if _pk:
        for _entry in all_entries:
            _cf = _entry.get('clientFile')
            if not _cf:
                continue
            _ck = _path_lookup_key(_cf)
            if not _ck:
                continue
            if _ck == _pk or _ck.endswith(_pk) or _pk.endswith(_ck):
                return _entry

    _base = os.path.basename(_path_str).lower()
    if _base:
        _matches = [
            _e for _e in all_entries
            if os.path.basename(_e.get('clientFile') or _e.get('depotFile') or '').lower() == _base
        ]
        if len(_matches) == 1:
            return _matches[0]
    return None


def _where_depot_path(disk_path, p4_user=None, p4_client=None):
    """Map a workspace disk path to //depot/path via p4 where."""
    _path = _normalize_disk_path(disk_path)
    if not _path:
        return None
    _res = _p4run('where', _path, p4_user=p4_user, p4_client=p4_client, ztag=True)
    for _rec in _res.get('tagRecords') or []:
        _depot = _rec.get('depotFile')
        if _depot:
            return str(_depot).split('#')[0]
    for _line in _res.get('lines') or []:
        _stripped = _strip_info_prefix(_line).strip()
        if not _stripped or _stripped.lower().startswith('error:'):
            continue
        _parts = _stripped.split()
        if _parts and str(_parts[0]).startswith('//'):
            return str(_parts[0]).split('#')[0]
    return None


def resolve_client_disk_path(path, p4_user=None, p4_client=None, force=False):
    """
    Resolve depot / UNC / disk path to the local path under the P4 client root.

    Scene popup revert uses browser paths (e.g. D:\\p4\\client\\...). p4 opened
    clientFile may be UNC while clientRoot is a mapped drive — p4 revert requires
    a path under clientRoot.
    """
    _path_str = str(path).strip() if path else ''
    if not _path_str:
        return None

    _norm = _normalize_disk_path(_path_str)
    if not _norm:
        return None

    _info = connection_info(force=force, p4_user=p4_user, p4_client=p4_client)
    _root = (_info or {}).get('clientRoot')
    if _root:
        try:
            _root_norm = os.path.normcase(os.path.normpath(_root))
            _norm_case = os.path.normcase(_norm)
            if _norm_case == _root_norm or _norm_case.startswith(_root_norm + os.sep):
                return _norm
        except Exception:
            pass

    _res = _p4run('where', _path_str, p4_user=p4_user, p4_client=p4_client, ztag=True)
    for _rec in _res.get('tagRecords') or []:
        for _key in ('path', 'clientFile'):
            _val = _rec.get(_key)
            if not _val:
                continue
            _s = str(_val).strip()
            if _s.startswith('//'):
                continue
            return os.path.normpath(_s)

    for _line in _res.get('lines') or []:
        _stripped = _strip_info_prefix(_line).strip()
        if not _stripped or _stripped.lower().startswith('error:'):
            continue
        _parts = _stripped.split()
        if len(_parts) >= 3:
            _local = str(_parts[2]).strip()
            if _local and not _local.startswith('//'):
                return os.path.normpath(_local)

    return _norm


def _unc_disk_prefix_from_pair(unc_path, disk_path):
    """Return (unc_prefix, disk_prefix) by stripping a shared trailing path, or None."""
    _unc = os.path.normpath(str(unc_path))
    _disk = os.path.normpath(str(disk_path))
    _unc_parts = _unc.split(os.sep)
    _disk_parts = _disk.split(os.sep)
    _shared = 0
    while _shared < len(_unc_parts) and _shared < len(_disk_parts):
        if os.path.normcase(_unc_parts[-1 - _shared]) != os.path.normcase(_disk_parts[-1 - _shared]):
            break
        _shared += 1
    if _shared <= 0:
        return None
    _unc_prefix = os.sep.join(_unc_parts[:-_shared]) if _shared < len(_unc_parts) else _unc
    _disk_prefix = os.sep.join(_disk_parts[:-_shared]) if _shared < len(_disk_parts) else _disk
    if not _unc_prefix or os.path.normcase(_unc_prefix) == os.path.normcase(_disk_prefix):
        return None
    return _unc_prefix, _disk_prefix


def _apply_unc_disk_prefix_map(path, prefix_map):
    if not path or not prefix_map:
        return None
    _norm = os.path.normpath(str(path))
    _case = os.path.normcase(_norm)
    for _unc_prefix, _disk_prefix in sorted(prefix_map.items(), key=lambda item: -len(item[0])):
        if _case == _unc_prefix:
            return _disk_prefix
        if _case.startswith(_unc_prefix + os.sep):
            return os.path.normpath(_disk_prefix + _norm[len(_unc_prefix):])
    return None


def _disk_path_for_fstat_client_file(client_file, p4_user=None, p4_client=None, prefix_map=None):
    """
    Map p4 fstat clientFile (UNC or disk) to the client-root disk path for cache keys.

    Learns a UNC-prefix → disk-prefix map from one resolve so tree/batch fstat
    does not call p4 where per file.
    """
    _norm = _normalize_disk_path(client_file)
    if not _norm:
        return None

    _info = connection_info(force=False, p4_user=p4_user, p4_client=p4_client)
    _root = (_info or {}).get('clientRoot')
    if _root:
        try:
            _root_norm = os.path.normpath(_root)
            _root_case = os.path.normcase(_root_norm)
            _norm_case = os.path.normcase(_norm)
            if _norm_case == _root_case or _norm_case.startswith(_root_case + os.sep):
                return _norm
        except Exception:
            pass

    if prefix_map is not None:
        _mapped = _apply_unc_disk_prefix_map(_norm, prefix_map)
        if _mapped:
            return _mapped

    _resolved = resolve_client_disk_path(_norm, p4_user=p4_user, p4_client=p4_client)
    if not _resolved:
        return _norm

    if prefix_map is not None and os.path.normcase(_resolved) != os.path.normcase(_norm):
        _pair = _unc_disk_prefix_from_pair(_norm, _resolved)
        if _pair:
            prefix_map[os.path.normcase(_pair[0])] = _pair[1]
    return _resolved


def _depot_file_line_from_opened_entry(entry):
    """Build //depot/path#action from a p4 opened record."""
    if not entry:
        return None
    _depot = entry.get('depotFile')
    if not _depot:
        return None
    _action = (entry.get('action') or 'edit').lower()
    return '{0}#{1}'.format(str(_depot).split('#')[0], _action)


def _depot_file_lines_for_opened_entries(entries, p4_user=None, p4_client=None, force=False):
    """Build //depot/path#action lines from p4 opened entry dicts."""
    _lines = []
    for _entry in entries or []:
        _line = _depot_file_line_from_opened_entry(_entry)
        if _line:
            _lines.append(_line)
            continue
        _cf = _entry.get('clientFile')
        if _cf:
            _line, _err = _resolve_depot_submit_line(
                _cf, p4_user=p4_user, p4_client=p4_client, force=force)
            if _err:
                return None, _err
            _lines.append(_line)
            continue
        return None, 'opened entry missing depot and client path'
    if not _lines:
        return None, 'no depot paths resolved'
    return _lines, None


def _resolve_depot_submit_line(path, p4_user=None, p4_client=None, force=False,
                               opened_by_client=None, opened_by_depot=None,
                               all_opened_entries=None):
    """
    Resolve //depot/path#action for submit/shelve forms.

    Prefer p4 opened records (reliable for UNC client paths where fstat args fail),
    then fstat on disk path, then depot-path fstat.
    Returns (line, error) — line like '//depot/foo.mb#edit'.
    """
    _path_str = str(path).strip() if path else ''
    if not _path_str:
        return None, 'path is empty'

    if opened_by_client is None or opened_by_depot is None:
        _opened = query_opened(p4_user=p4_user, p4_client=p4_client, force=force)
        opened_by_client, opened_by_depot, _all_opened = _build_opened_path_indexes(_opened)
    elif all_opened_entries is None:
        _all_opened = list(opened_by_client.values())
    else:
        _all_opened = all_opened_entries

    _opened_entry = _lookup_opened_entry(
        _path_str, opened_by_client, opened_by_depot, all_entries=_all_opened)
    if _opened_entry and _opened_entry.get('depotFile'):
        _depot = str(_opened_entry['depotFile']).split('#')[0]
        _action = (_opened_entry.get('action') or 'edit').lower()
        return '{0}#{1}'.format(_depot, _action), None

    if _path_str.startswith('//'):
        _depot = _path_str.split('#')[0]
        _res = _p4run(
            'fstat', _depot, p4_user=p4_user, p4_client=p4_client, ztag=True)
        _rec = (_res.get('tagRecords') or [None])[0] or {}
        _action = (_rec.get('action') or 'edit').lower()
        return '{0}#{1}'.format(_depot, _action), None

    _stat = query_file_status(
        _path_str, p4_user=p4_user, p4_client=p4_client, force=force)
    _depot = _stat.get('depotFile')
    if _depot:
        _action = (_stat.get('openAction') or 'edit').lower()
        return '{0}#{1}'.format(_depot.split('#')[0], _action), None

    _where_depot = _where_depot_path(_path_str, p4_user=p4_user, p4_client=p4_client)
    if _where_depot:
        _opened_entry = _lookup_opened_entry(
            _where_depot, opened_by_client, opened_by_depot, all_entries=_all_opened)
        _action = (_opened_entry.get('action') if _opened_entry else None) or 'edit'
        return '{0}#{1}'.format(_where_depot, str(_action).lower()), None

    return None, 'no depot path for {0}'.format(_path_str)


def _depot_keys_for_submit(paths, p4_user=None, p4_client=None, force=False):
    """Map disk paths to lowercase depot keys for changelist spec filtering."""
    _keys = set()
    _opened = query_opened(p4_user=p4_user, p4_client=p4_client, force=force)
    _by_client, _by_depot, _all_opened = _build_opened_path_indexes(_opened)
    for _path in paths or []:
        _line, _err = _resolve_depot_submit_line(
            _path,
            p4_user=p4_user,
            p4_client=p4_client,
            force=force,
            opened_by_client=_by_client,
            opened_by_depot=_by_depot,
            all_opened_entries=_all_opened,
        )
        if _err:
            return None, _err
        _key = _depot_path_key(_line.split('#')[0])
        if _key:
            _keys.add(_key)
    if not _keys:
        return None, 'no depot paths resolved'
    return _keys, None


def _depot_file_lines_for_paths(paths, p4_user=None, p4_client=None, force=False):
    """Build //depot/path#action lines for a shelve/change form from disk paths."""
    _lines = []
    _opened = query_opened(p4_user=p4_user, p4_client=p4_client, force=force)
    _by_client, _by_depot, _all_opened = _build_opened_path_indexes(_opened)
    for _path in paths or []:
        _line, _err = _resolve_depot_submit_line(
            _path,
            p4_user=p4_user,
            p4_client=p4_client,
            force=force,
            opened_by_client=_by_client,
            opened_by_depot=_by_depot,
            all_opened_entries=_all_opened,
        )
        if _err:
            return None, _err
        _lines.append(_line)
    if not _lines:
        return None, 'no depot paths resolved'
    return _lines, None


def _depot_file_lines_from_spec(spec_text):
    """Extract //depot/path#action lines from a p4 change spec Files section."""
    _lines = []
    _section = None
    for _line in (spec_text or '').splitlines():
        if _line.startswith('Files:'):
            _section = 'files'
            continue
        if _section == 'files':
            _stripped = _line.strip()
            if _stripped.startswith('//'):
                _lines.append(_stripped.split()[0])
                continue
            if not _stripped:
                continue
            _section = None
    return _lines


def _build_new_change_form_spec(p4_client, depot_file_lines, description):
    """Build a Change: new form for p4 shelve -i (default changelist cannot be shelved via -i)."""
    _out = [
        'Change: new',
        'Client: {0}'.format(p4_client),
        '',
    ]
    _out.extend(_format_change_spec_description_lines(description))
    if depot_file_lines:
        _out.append('')
        _out.append('Files:')
        for _line in depot_file_lines:
            _out.append('\t' + _line)
    return '\n'.join(_out) + '\n'


def _build_default_change_submit_spec(p4_client, depot_file_lines, description):
    """Build Change: default form — NOT valid for p4 submit -i (P4: Default change unknown). Kept for reference."""
    _out = [
        'Change: default',
        'Client: {0}'.format(p4_client),
        '',
    ]
    _out.extend(_format_change_spec_description_lines(description))
    if depot_file_lines:
        _out.append('')
        _out.append('Files:')
        for _line in depot_file_lines:
            _out.append('\t' + _line)
    return '\n'.join(_out) + '\n'


def _build_changelist_form_spec(spec_text, depot_keys, description):
    """
    Filter a p4 change spec to selected depot files and set Description.

    depot_keys: set of lowercase depot paths without #rev.
    """
    if not spec_text:
        return ''
    _lines = spec_text.splitlines()
    _header = []
    _kept_files = []
    _section = None

    for _line in _lines:
        if _line.startswith('Description:'):
            _section = 'description'
            continue
        if _line.startswith('Files:'):
            _section = 'files'
            continue
        if _section == 'description':
            if _line.startswith('\t') or (_line.startswith(' ') and _line.strip()):
                continue
            if not _line.strip():
                continue
            _section = None
        if _section == 'files':
            _stripped = _line.strip()
            if _stripped.startswith('//'):
                _key = _depot_path_key(_stripped.split()[0])
                if _key and _key in depot_keys:
                    _kept_files.append('\t' + _stripped.split()[0])
                continue
            if not _stripped:
                continue
            _section = None
        if _section is None:
            _header.append(_line)

    _out = list(_header)
    while _out and not _out[-1].strip():
        _out.pop()
    _out.append('')
    _out.extend(_format_change_spec_description_lines(description))
    if _kept_files:
        _out.append('')
        _out.append('Files:')
        _out.extend(_kept_files)
    return '\n'.join(_out) + '\n'


def query_change_description(change, p4_user=None, p4_client=None):
    """Return Description field from a pending changelist spec."""
    _spec, _err = _fetch_change_spec(change, p4_user=p4_user, p4_client=p4_client)
    if _err or not _spec:
        return ''
    return _parse_change_spec_description(_spec)


def submit_prepare_action(file_dat):
    """
    Return None when file is opened and ready to submit,
    'add' or 'checkout' when a prepare step is needed,
    else a blocked reason string.
    """
    if not file_dat:
        return 'status unknown'
    if file_dat.get('checkedOut'):
        return None
    if file_dat.get('notInClient'):
        return 'not in client view'
    if file_dat.get('lockedByOther'):
        return 'locked or open elsewhere'
    if file_dat.get('outOfDate'):
        return 'out of date — sync first'
    if file_dat.get('notOnDepot') or not file_dat.get('onDepot'):
        return 'add'
    return 'checkout'


def submit_skip_reason(file_dat):
    """
    Return None when file_dat is opened and can be submitted, else a short reason string.
    """
    _action = submit_prepare_action(file_dat)
    if _action is None:
        return None
    if _action in ('add', 'checkout'):
        return 'not on depot — use Add first' if _action == 'add' else 'not checked out — use Checkout first'
    return _action


def _sync_target_head(dir_path):
    """Client path for recursive sync to head, e.g. D:/proj/Char/Hondo/...#head"""
    _dir = _normalize_disk_path(dir_path)
    if not _dir:
        return None
    if _dir.endswith('...#head'):
        return _dir
    if _dir.endswith('...'):
        return _dir + '#head'
    return os.path.join(_dir, '...#head')


def _fstat_target_recursive(dir_path):
    """Client path for recursive fstat, e.g. D:/proj/content/..."""
    _dir = _normalize_disk_path(dir_path)
    if not _dir:
        return None
    if _dir.endswith('...'):
        return _dir
    return os.path.join(_dir, '...')


def _p4run_sync(target, force=False, p4_user=None, p4_client=None, progress_cb=None, cancel_cb=None,
                progress_every=25):
    """
    Run p4 sync with streamed stdout so callers can update UI during long syncs.

    progress_cb(count, line) -> True to cancel.
    cancel_cb() -> True to cancel.
    progress_every: UI callback interval in sync output lines (reduces Maya overhead).
    """
    _cmd = ['p4', '-s']
    if p4_user:
        _cmd.extend(['-u', str(p4_user)])
    if p4_client:
        _cmd.extend(['-c', str(p4_client)])
    if force:
        _cmd.extend(['sync', '-f', target])
    else:
        _cmd.extend(['sync', target])

    try:
        _proc = subprocess.Popen(
            _cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            **_P4_SUBPROCESS_KW,
        )
    except FileNotFoundError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': 'p4 executable not found',
            'exitCode': -1,
            'cancelled': False,
            'error': str(err),
        }
    except OSError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': str(err),
            'exitCode': -1,
            'cancelled': False,
            'error': str(err),
        }

    _lines = []
    _cancelled = False
    log.debug('p4 sync | {0}'.format(' '.join(_cmd)))

    def _cancelled_out():
        nonlocal _cancelled
        _cancelled = True
        try:
            _proc.kill()
        except Exception:
            pass
        try:
            _proc.wait(timeout=5)
        except Exception:
            pass
        return {
            'ok': False,
            'lines': _lines,
            'stderr': 'cancelled',
            'exitCode': -1,
            'cancelled': True,
        }

    try:
        while True:
            if cancel_cb and cancel_cb():
                return _cancelled_out()
            _raw = _proc.stdout.readline()
            if not _raw:
                if _proc.poll() is not None:
                    break
                continue
            try:
                _text = _raw.decode('utf-8', errors='replace')
            except AttributeError:
                _text = str(_raw)
            _line = _strip_info_prefix(_text.rstrip('\r\n'))
            if not _line:
                continue
            _lines.append(_line)
            _count = len(_lines)
            if progress_cb and (
                    _count == 1
                    or progress_every <= 1
                    or _count % max(int(progress_every), 1) == 0):
                if progress_cb(_count, _line):
                    return _cancelled_out()
    except Exception as err:
        try:
            _proc.kill()
        except Exception:
            pass
        return {
            'ok': False,
            'lines': _lines,
            'stderr': str(err),
            'exitCode': -1,
            'cancelled': _cancelled,
            'error': str(err),
        }

    try:
        _proc.wait(timeout=5)
    except Exception:
        pass

    _exit = _proc.returncode
    _err_lines = [l for l in _lines if l.lower().startswith('error:')]
    if _err_lines:
        _err = _err_lines[0]
    else:
        _err = ''
    _errors = list(_err_lines)
    _ok = _exit == 0 and not _errors and not _cancelled

    if progress_cb and _lines and _ok and not _cancelled:
        try:
            progress_cb(len(_lines), _lines[-1])
        except Exception:
            pass

    return {
        'ok': _ok,
        'lines': _lines,
        'stderr': _normalize_error(_err),
        'exitCode': _exit,
        'cancelled': _cancelled,
    }


def _p4run_fstat_recursive(target, p4_user=None, p4_client=None, progress_cb=None, record_cb=None, cancel_cb=None):
    """
    Run p4 fstat on a recursive client target (path/...) with streamed stdout.

    progress_cb(record_count, client_file) -> True to cancel (legacy, if record_cb omitted).
    record_cb(tag_dict) -> True to cancel — preferred; one call per parsed fstat record.
    cancel_cb() -> True to cancel.
    """
    _cmd = ['p4']
    if p4_user:
        _cmd.extend(['-u', str(p4_user)])
    if p4_client:
        _cmd.extend(['-c', str(p4_client)])
    _cmd.extend(['-ztag', 'fstat', target])

    try:
        _proc = subprocess.Popen(
            _cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            **_P4_SUBPROCESS_KW,
        )
    except FileNotFoundError as err:
        return {
            'ok': False,
            'stderr': 'p4 executable not found',
            'exitCode': -1,
            'cancelled': False,
            'tagRecords': [],
            'fileCount': 0,
            'error': str(err),
        }
    except OSError as err:
        return {
            'ok': False,
            'stderr': str(err),
            'exitCode': -1,
            'cancelled': False,
            'tagRecords': [],
            'fileCount': 0,
            'error': str(err),
        }

    _records = []
    _block = []
    _count = 0
    _cancelled = False
    _err_lines = []
    log.debug('p4 fstat | {0}'.format(' '.join(_cmd)))

    def _cancelled_out():
        nonlocal _cancelled
        _cancelled = True
        try:
            _proc.kill()
        except Exception:
            pass
        try:
            _proc.wait(timeout=5)
        except Exception:
            pass
        return {
            'ok': False,
            'stderr': 'cancelled',
            'exitCode': -1,
            'cancelled': True,
            'tagRecords': _records,
            'fileCount': _count,
        }

    def _flush_block():
        nonlocal _count
        if not _block:
            return False
        _rec = _parse_tag_block(_block)
        _block[:] = []
        if not _rec:
            return False
        _records.append(_rec)
        _count += 1
        if record_cb:
            if record_cb(_rec):
                return True
        elif progress_cb and progress_cb(_count, _rec.get('clientFile') or ''):
            return True
        return False

    try:
        while True:
            if cancel_cb and cancel_cb():
                return _cancelled_out()
            _raw = _proc.stdout.readline()
            if not _raw:
                if _proc.poll() is not None:
                    break
                continue
            try:
                _text = _raw.decode('utf-8', errors='replace')
            except AttributeError:
                _text = str(_raw)
            _line = _strip_info_prefix(_text.rstrip('\r\n'))
            if not _line.strip() or _line.strip().startswith('exit:'):
                if _flush_block():
                    return _cancelled_out()
                continue
            if _line.strip().lower().startswith('error:'):
                _err_lines.append(_line.strip())
                continue
            if not _line.startswith('...'):
                if _flush_block():
                    return _cancelled_out()
                continue
            _block.append(_line)
    except Exception as err:
        try:
            _proc.kill()
        except Exception:
            pass
        return {
            'ok': False,
            'stderr': str(err),
            'exitCode': -1,
            'cancelled': _cancelled,
            'tagRecords': _records,
            'fileCount': _count,
            'error': str(err),
        }

    if _flush_block():
        return _cancelled_out()

    try:
        _proc.wait(timeout=5)
    except Exception:
        pass

    _exit = _proc.returncode
    _err = _err_lines[0] if _err_lines else ''
    _ok = _exit == 0 and not _err_lines and not _cancelled

    return {
        'ok': _ok,
        'stderr': _normalize_error(_err),
        'exitCode': _exit,
        'cancelled': _cancelled,
        'tagRecords': _records,
        'fileCount': _count,
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
            log.debug('Using cached Perforce status (project)')
            return _cached_status

    log.debug('Getting Perforce status (project)...')
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
        _change, _status, _desc = _parse_change_list_line(_line)
        if _change is None:
            continue
        _changes.append({
            'change': _change,
            'status': _status or 'pending',
            'description': (_desc or '').strip(),
            'line': _line,
        })

    return {'changes': _changes}


def _parse_change_list_line(line):
    """Parse p4 changes text line → (change int, status, description) or Nones."""
    _line = (line or '').strip()
    if not _line or _line.lower().startswith('error:'):
        return None, None, None
    _m = _CHANGE_LINE_RE.match(_line)
    if not _m:
        return None, None, None
    try:
        _change = int(_m.group('change'))
    except (TypeError, ValueError):
        return None, None, None
    _status = _m.group('status')
    _desc = ''
    _rest = _line[_m.end():].strip()
    if _rest.startswith("'") and _rest.endswith("'") and len(_rest) > 1:
        _desc = _rest[1:-1]
    elif _rest.startswith("'"):
        _desc = _rest[1:]
    return _change, _status, _desc


def _parse_describe_indexed_files(tag_dict, change):
    """Extract shelved/affected files from p4 describe -ztag indexed fields (depotFile0, …)."""
    _entries = []
    if not tag_dict:
        return _entries
    _i = 0
    while _i < 10000:
        _depot = tag_dict.get('depotFile{0}'.format(_i))
        if not _depot:
            break
        _rev = tag_dict.get('rev{0}'.format(_i))
        try:
            _rev = int(_rev)
        except (TypeError, ValueError):
            pass
        _depot_str = str(_depot).split('#')[0]
        _entries.append({
            'depotFile': _depot_str,
            'clientFile': tag_dict.get('clientFile{0}'.format(_i)),
            'rev': _rev,
            'action': tag_dict.get('action{0}'.format(_i)) or 'edit',
            'change': change,
            'type': tag_dict.get('type{0}'.format(_i)),
        })
        _i += 1
    return _entries


def _parse_describe_file_lines(lines, change):
    """Parse //depot/path#rev action lines from p4 describe text output."""
    _entries = []
    _seen = set()
    for _raw in lines or []:
        _stripped = _strip_info_prefix(_raw).strip()
        if _stripped.startswith('...'):
            _stripped = _stripped[3:].strip()
        if not _stripped.startswith('//'):
            continue
        _parts = _stripped.split()
        if not _parts:
            continue
        _depot_part = _parts[0]
        _depot = _depot_part.split('#')[0]
        _key = _depot.lower()
        if _key in _seen:
            continue
        _seen.add(_key)
        _rev = None
        if '#' in _depot_part:
            try:
                _rev = int(_depot_part.rsplit('#', 1)[1])
            except (TypeError, ValueError):
                pass
        _action = _parts[1] if len(_parts) > 1 else 'edit'
        _entries.append({
            'depotFile': _depot,
            'clientFile': None,
            'rev': _rev,
            'action': _action,
            'change': change,
            'type': None,
        })
    return _entries


def _describe_shelved_entries(change, p4_user=None, p4_client=None):
    """Return list of shelved file entry dicts for a changelist."""
    _entries = []
    _stderr = None
    _res = _p4run(
        'describe', '-sS', str(change),
        p4_user=p4_user, p4_client=p4_client, ztag=True,
    )
    if _res.get('ok'):
        for _rec in _res.get('tagRecords') or []:
            _entries.extend(_parse_describe_indexed_files(_rec, change))
            if _rec.get('depotFile'):
                _rev = _rec.get('rev')
                try:
                    _rev = int(_rev)
                except (TypeError, ValueError):
                    pass
                _entries.append({
                    'depotFile': str(_rec.get('depotFile')).split('#')[0],
                    'clientFile': _rec.get('clientFile'),
                    'rev': _rev,
                    'action': _rec.get('action') or 'edit',
                    'change': change,
                    'type': _rec.get('type'),
                })
        if not _entries:
            _entries.extend(_parse_describe_indexed_files(_res.get('tag') or {}, change))
        if not _entries:
            _entries.extend(_parse_describe_file_lines(_res.get('lines'), change))
    else:
        _stderr = _res.get('stderr') or 'p4 describe -sS failed'

    if not _entries:
        _res_plain = _p4run(
            'describe', '-sS', str(change),
            p4_user=p4_user, p4_client=p4_client, ztag=False,
        )
        if _res_plain.get('ok'):
            _entries.extend(_parse_describe_file_lines(_res_plain.get('lines'), change))
        elif not _stderr:
            _stderr = _res_plain.get('stderr') or 'p4 describe -sS failed'

    if _stderr and not _entries:
        return _entries, _stderr

    _deduped = []
    _seen = set()
    for _entry in _entries:
        _key = (_entry.get('depotFile') or '').lower()
        if not _key or _key in _seen:
            continue
        _seen.add(_key)
        _deduped.append(_entry)
    return _deduped, None


def query_shelved(p4_user=None, p4_client=None, force=False):
    """
    Shelved changelists and files for user/client (p4 changes -s shelved + describe -sS).

    Returns dict: changes {cl: {change, description, entries, line}}, total, rawCount.
    """
    _empty = {'changes': {}, 'total': 0, 'rawCount': 0}
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return dict(_empty, error=_err)

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return dict(_empty, error='p4 info failed')

    _res = _p4run(
        'changes', '-s', 'shelved', '-u', _user, '-c', _client,
        p4_user=_user, p4_client=_client, ztag=False, use_s=True,
    )
    if not _res['ok']:
        return dict(_empty, error=_res.get('stderr') or 'p4 changes -s shelved failed')

    _changes = {}
    _file_count = 0
    _cl_count = 0

    for _line in _res.get('lines') or []:
        _change, _status, _desc = _parse_change_list_line(_line)
        if _change is None:
            continue
        _cl_count += 1
        _entries, _desc_err = _describe_shelved_entries(
            _change, p4_user=_user, p4_client=_client)
        if _desc_err and not _entries:
            log.warning('P4 shelved CL {0}: {1}'.format(_change, _desc_err))
        if not _desc:
            _desc = query_change_description(_change, p4_user=_user, p4_client=_client)
        _file_count += len(_entries)
        _changes[_change] = {
            'change': _change,
            'description': _desc or '',
            'entries': _entries,
            'line': _line.strip(),
            'status': _status,
        }

    return {
        'changes': _changes,
        'total': _file_count,
        'rawCount': _cl_count,
    }


def query_file_status(disk_path, p4_user=None, p4_client=None, force=False):
    """
    Workspace membership and depot status for a disk path (p4 -u -c -ztag fstat).

    Returns dict including:
      inClient, onDepot, checkedOut, outOfDate, synced, lockedByOther,
      statusLabels, statusSummary, headRev, haveRev, openAction, otherOpen, ...
    """
    _norm = _normalize_disk_path(disk_path)
    if not _norm:
        return dict(_new_file_status_out(disk_path), error='path is empty')
    _result = query_files_status(
        [_norm], p4_user=p4_user, p4_client=p4_client, force=force)
    return _result.get(_norm) or dict(_new_file_status_out(_norm), error='p4 fstat failed')


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


def _fstat_cache_store():
    _store = _cache.get('fstat_by_path')
    if _store is None:
        _store = {}
        _cache['fstat_by_path'] = _store
    return _store


def _fstat_cache_key(p4_user, p4_client, normpath):
    return (p4_user or '', p4_client or '', _path_lookup_key(normpath))


def _path_key_under_root(path_key, root_key):
    if not path_key or not root_key:
        return False
    if path_key == root_key:
        return True
    return path_key.startswith(root_key + os.sep)


def _fstat_cache_depot_skip_and_unknown(root_path, p4_user, p4_client):
    """
    Session fstat entries under root_path.

    Returns (depot_skip_keys, cached_unknown_entries).
    depot_skip_keys: paths already classified — skip batch fstat (same role as depot_paths).
    cached_unknown_entries: known unknowns from cache — include without re-query.
    """
    _root = _normalize_disk_path(root_path)
    _root_key = _path_lookup_key(_root)
    if not _root_key:
        return set(), []

    _store = _fstat_cache_store()
    if not _store:
        return set(), []

    _depot_keys = set()
    _unknown_entries = []
    for _key, _dat in _store.items():
        if len(_key) < 3:
            continue
        if _key[0] != (p4_user or '') or _key[1] != (p4_client or ''):
            continue
        _path_key = _key[2]
        if not _path_key_under_root(_path_key, _root_key):
            continue
        if not _dat:
            continue
        if _is_unknown_file(_dat):
            _norm = _normalize_disk_path(_dat.get('path'))
            if _norm and os.path.isfile(_norm):
                _unknown_entries.append({'path': _norm, 'dat': dict(_dat)})
            continue
        if _dat.get('notInClient'):
            _depot_keys.add(_path_key)
            continue
        if _dat.get('onDepot') or not _dat.get('notOnDepot'):
            _depot_keys.add(_path_key)
            continue
        if classify_file_status_ui(_dat) is not None:
            _depot_keys.add(_path_key)
    return _depot_keys, _unknown_entries


def invalidate_fstat_paths(disk_paths, p4_user=None, p4_client=None):
    """Drop cached fstat entries for specific disk paths (current user/client when omitted)."""
    _store = _fstat_cache_store()
    if not _store:
        return
    for _raw in disk_paths or []:
        _norm = _normalize_disk_path(_raw)
        if not _norm:
            continue
        _lookup = _path_lookup_key(_norm)
        _drop = []
        for _key in _store:
            if len(_key) < 3 or _key[2] != _lookup:
                continue
            if p4_user is not None and _key[0] != (p4_user or ''):
                continue
            if p4_client is not None and _key[1] != (p4_client or ''):
                continue
            _drop.append(_key)
        for _key in _drop:
            del _store[_key]


def flush_fstat_cache(p4_user=None, p4_client=None):
    """Clear session fstat cache (all entries, or scoped to user/client)."""
    _store = _fstat_cache_store()
    if not _store:
        return
    if p4_user is None and p4_client is None:
        _store.clear()
        flush_unknown_cache()
        return
    _drop = []
    for _key in _store:
        if p4_user is not None and _key[0] != (p4_user or ''):
            continue
        if p4_client is not None and _key[1] != (p4_client or ''):
            continue
        _drop.append(_key)
    for _key in _drop:
        del _store[_key]


def invalidate_fstat_directory(dir_path, p4_user=None, p4_client=None):
    """Drop cached fstat entries for all files under a directory (column Refresh)."""
    _dir = _normalize_disk_path(dir_path)
    if not _dir:
        return
    _store = _fstat_cache_store()
    if not _store:
        return
    _dir_key = _path_lookup_key(_dir)
    _prefix = _dir_key + os.sep
    _drop = []
    for _key in _store:
        if len(_key) < 3:
            continue
        _path_key = _key[2]
        if _path_key != _dir_key and not _path_key.startswith(_prefix):
            continue
        if p4_user is not None and _key[0] != (p4_user or ''):
            continue
        if p4_client is not None and _key[1] != (p4_client or ''):
            continue
        _drop.append(_key)
    for _key in _drop:
        del _store[_key]


def _query_files_status_batch(paths, p4_user, p4_client):
    """Uncached batch fstat for one chunk of paths."""
    if not paths:
        return {}
    _res = _p4run('fstat', *paths, p4_user=p4_user, p4_client=p4_client, ztag=True)
    _prefix_map = {}
    _by_key = {}
    for _rec in _res.get('tagRecords') or []:
        _client_file = _rec.get('clientFile')
        if not _client_file:
            continue
        _resolved = _disk_path_for_fstat_client_file(
            _client_file, p4_user=p4_user, p4_client=p4_client, prefix_map=_prefix_map)
        if not _resolved:
            continue
        _dat = _file_status_from_fstat_tag(_resolved, _rec)
        _lookup = _path_lookup_key(_resolved)
        if _lookup:
            _by_key[_lookup] = _dat
        _orig = _path_lookup_key(_client_file)
        if _orig and _orig not in _by_key:
            _by_key[_orig] = _dat

    _out = {}
    for _norm in paths:
        _lookup = _path_lookup_key(_norm)
        if _lookup in _by_key:
            _dat = dict(_by_key[_lookup])
            _dat['path'] = _norm
            _out[_norm] = _dat
        else:
            _out[_norm] = _fstat_missing_path_status(_norm, _res)
    _enrich_status_with_depot_opens(_out, p4_user, p4_client)
    return _out


def count_fstat_cache_misses(disk_paths, p4_user=None, p4_client=None, force=False):
    """
    Count disk paths not in session fstat cache (0 = fully cached, no p4 fstat needed).

    Same path normalization and cache keys as query_files_status.
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
        return 0

    if force:
        return len(_paths)

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err or not is_available(force=False, p4_user=_user, p4_client=_client):
        return 0

    _store = _fstat_cache_store()
    _miss = 0
    for _norm in _paths:
        if _store.get(_fstat_cache_key(_user, _client, _norm)) is None:
            _miss += 1
    return _miss


def query_files_status(disk_paths, p4_user=None, p4_client=None, force=False, progress_cb=None):
    """
    Batch workspace / depot status for disk paths (chunked p4 -u -c -ztag fstat).

    Returns dict normpath -> status dict (same shape as query_file_status).
    Session-cached per (user, client, path) unless force=True or path invalidated.
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

    if force:
        invalidate_fstat_paths(_paths, p4_user=p4_user, p4_client=p4_client)

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {_norm: dict(_new_file_status_out(_norm), error=_err) for _norm in _paths}

    if not is_available(force=False, p4_user=_user, p4_client=_client):
        return {
            _norm: dict(_new_file_status_out(_norm), error='p4 info failed')
            for _norm in _paths
        }

    _store = _fstat_cache_store()
    _out = {}
    _miss = []
    for _norm in _paths:
        _cache_key = _fstat_cache_key(_user, _client, _norm)
        _cached = _store.get(_cache_key)
        if _cached is not None:
            _out[_norm] = dict(_cached)
        else:
            _miss.append(_norm)

    _num_chunks = max(1, (len(_miss) + FSTAT_QUERY_CHUNK - 1) // FSTAT_QUERY_CHUNK) if _miss else 0
    _chunk_idx = 0
    for _i in range(0, len(_miss), FSTAT_QUERY_CHUNK):
        if progress_cb:
            _chunk_idx += 1
            if progress_cb(_chunk_idx, _num_chunks, 'Perforce file status'):
                break
        _chunk = _miss[_i:_i + FSTAT_QUERY_CHUNK]
        _fresh = _query_files_status_batch(_chunk, _user, _client)
        for _norm, _dat in _fresh.items():
            _out[_norm] = _dat
            _store[_fstat_cache_key(_user, _client, _norm)] = dict(_dat)
    return _out


def _fstat_dir_mask_skip(name, dir_mask):
    if not name or not dir_mask:
        return False
    _lower = name.lower()
    for _m in dir_mask:
        if _m and _lower == str(_m).lower():
            return True
    return False


def _path_has_masked_dir_component(path, root, dir_mask):
    if not path or not root or not dir_mask:
        return False
    try:
        _rel = os.path.relpath(path, root)
    except Exception:
        return False
    if _rel in ('.', ''):
        return False
    for _part in _rel.replace('/', os.sep).split(os.sep):
        if _fstat_dir_mask_skip(_part, dir_mask):
            return True
    return False


def _collect_fstat_cache_dirs(root, dir_mask=None):
    """Fast local walk — directory list for cache progress (no p4 calls)."""
    _root = _normalize_disk_path(root)
    if not _root or not os.path.isdir(_root):
        return []
    _mask = [m for m in (dir_mask or []) if m]
    _dirs = []
    try:
        for _walk_root, _dirnames, _filenames in os.walk(_root):
            _dirnames[:] = [d for d in _dirnames if not _fstat_dir_mask_skip(d, _mask)]
            _dirs.append(os.path.normpath(_walk_root))
    except Exception:
        return [_root]
    return _dirs


def fetch_fstat_tree_records(
        root_path,
        p4_user=None,
        p4_client=None,
        dir_mask=None,
        progress_cb=None,
        cancel_cb=None):
    """
    Run recursive p4 fstat and return storable cache records (no session write).

    progress_cb(record_count, files_total, current_path, dirs_done=0, dir_total=0, current_dir=None)
        files_total is always 0 while fetching. Return True to cancel.
    cancel_cb() -> True to cancel.

    Returns dict: ok, cancelled, path, records [{norm, dat}], fileCount, fileTotal, dirTotal, error.
    """
    _root = _normalize_disk_path(root_path)
    _result = {
        'ok': False,
        'cancelled': False,
        'path': _root,
        'records': [],
        'fileCount': 0,
        'fileTotal': 0,
        'dirTotal': 0,
        'error': None,
    }
    if not _root or not os.path.isdir(_root):
        _result['error'] = 'not a directory'
        return _result

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _result['error'] = _err
        return _result

    if not is_available(force=False, p4_user=_user, p4_client=_client):
        _result['error'] = 'p4 info failed'
        return _result

    _target = _fstat_target_recursive(_root)
    if not _target:
        _result['error'] = 'path is empty'
        return _result

    _mask = [m for m in (dir_mask or []) if m]
    _dir_list = _collect_fstat_cache_dirs(_root, _mask)
    _dir_total = len(_dir_list)
    _dir_index = {d: i for i, d in enumerate(_dir_list)}
    _result['dirTotal'] = _dir_total
    _result['dirList'] = _dir_list
    _records = []
    _files_fetched = 0
    _last_path = _root
    _dirs_done = 0
    _last_dir = None
    _ui_tick = 0
    _prefix_map = {}

    if progress_cb:
        progress_cb(0, 0, _root, 0, _dir_total, _root)

    def _ui_every():
        if _files_fetched < 50:
            return 1
        if _files_fetched < 500:
            return 5
        return 20

    def _on_fstat_record(rec):
        nonlocal _files_fetched, _last_path, _dirs_done, _last_dir, _ui_tick, _result
        if cancel_cb and cancel_cb():
            _result['cancelled'] = True
            return True
        _client_file = rec.get('clientFile')
        if not _client_file:
            return False
        _norm = _disk_path_for_fstat_client_file(
            _client_file, p4_user=_user, p4_client=_client, prefix_map=_prefix_map)
        if not _norm:
            return False
        if _mask and _path_has_masked_dir_component(_norm, _root, _mask):
            return False
        _dat = _file_status_from_fstat_tag(_norm, rec)
        _dat['path'] = _norm
        _records.append({'norm': _norm, 'dat': dict(_dat)})
        _files_fetched += 1
        _last_path = _norm
        _parent = os.path.normpath(os.path.dirname(_norm))
        if _parent != _last_dir:
            _last_dir = _parent
            _idx = _dir_index.get(_parent)
            if _idx is not None:
                _dirs_done = _idx + 1
        _ui_tick += 1
        if progress_cb and (
                _files_fetched == 1
                or _ui_tick % _ui_every() == 0):
            if progress_cb(
                    _files_fetched, 0, _norm, _dirs_done, _dir_total, _parent):
                _result['cancelled'] = True
                return True
        return False

    log.info('P4 fstat fetch | {0}'.format(_target))
    _res = _p4run_fstat_recursive(
        _target,
        p4_user=_user,
        p4_client=_client,
        record_cb=_on_fstat_record,
        cancel_cb=cancel_cb,
    )

    if _res.get('cancelled'):
        _result['cancelled'] = True

    if not _res.get('ok') and not _result.get('cancelled'):
        _result['error'] = _res.get('stderr') or 'p4 fstat failed'
        return _result

    _result['records'] = _records
    _result['fileCount'] = _files_fetched
    _result['fileTotal'] = _files_fetched
    _result['ok'] = not _result['cancelled']
    return _result


def store_fstat_cache_records(records, p4_user=None, p4_client=None, start=0, end=None):
    """
    Write pre-built fstat entries into the session cache.

    Each item in records: {norm, dat} as returned by fetch_fstat_tree_records.
    Optional start/end slice for batched UI updates.
    """
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'error': _err, 'fileCount': 0}
    _store = _fstat_cache_store()
    _count = 0
    _slice = records[start:end] if end is not None else records
    for _rec in _slice or []:
        _norm = _rec.get('norm')
        _dat = _rec.get('dat')
        if not _norm or not _dat:
            continue
        _store[_fstat_cache_key(_user, _client, _norm)] = dict(_dat)
        _count += 1
    return {'ok': True, 'fileCount': _count, 'endIndex': (start or 0) + _count}


def store_fstat_cache_record(record, p4_user=None, p4_client=None):
    """Store one fstat cache entry {norm, dat}."""
    return store_fstat_cache_records([record], p4_user=p4_user, p4_client=p4_client)


def _unknown_cache_store():
    _store = _cache.get('unknown_files')
    if _store is None:
        _store = {}
        _cache['unknown_files'] = _store
    return _store


def _unknown_cache_key(p4_user, p4_client, root):
    _root = _normalize_disk_path(root)
    _lookup = _path_lookup_key(_root) if _root else ''
    return (p4_user or '', p4_client or '', _lookup or '')


def _is_unknown_file(dat):
    return classify_file_status_ui(dat) == 'unknown'


def _collect_disk_files(root, dir_mask=None):
    """Local file paths under root (respecting dir_mask), no p4 calls."""
    _root = _normalize_disk_path(root)
    if not _root or not os.path.isdir(_root):
        return []
    _mask = [m for m in (dir_mask or []) if m]
    _files = []
    _seen = set()
    try:
        for _walk_root, _dirnames, _filenames in os.walk(_root):
            _dirnames[:] = [d for d in _dirnames if not _fstat_dir_mask_skip(d, _mask)]
            for _fname in _filenames:
                _path = os.path.normpath(os.path.join(_walk_root, _fname))
                if not os.path.isfile(_path):
                    continue
                if _mask and _path_has_masked_dir_component(_path, _root, _mask):
                    continue
                _key = _path_lookup_key(_path)
                if not _key or _key in _seen:
                    continue
                _seen.add(_key)
                _files.append(_path)
    except Exception:
        pass
    return _files


def flush_unknown_cache(p4_user=None, p4_client=None):
    """Clear session unknown-files cache (all entries, or scoped to user/client)."""
    _store = _unknown_cache_store()
    if not _store:
        return
    if p4_user is None and p4_client is None:
        _store.clear()
        return
    _drop = []
    for _key in _store:
        if p4_user is not None and _key[0] != (p4_user or ''):
            continue
        if p4_client is not None and _key[1] != (p4_client or ''):
            continue
        _drop.append(_key)
    for _key in _drop:
        del _store[_key]


def invalidate_unknown_paths(disk_paths, p4_user=None, p4_client=None):
    """Drop listed paths from all unknown-file cache entries for user/client."""
    _user = p4_user
    _client = p4_client
    if _user is None or _client is None:
        _user, _client = resolve_connection(p4_user, p4_client)
    _store = _unknown_cache_store()
    if not _store:
        return
    _drop_keys = {_path_lookup_key(_normalize_disk_path(_p)) for _p in (disk_paths or [])}
    _drop_keys.discard(None)
    if not _drop_keys:
        return
    for _cache_key, _dat in list(_store.items()):
        if _cache_key[0] != (_user or '') or _cache_key[1] != (_client or ''):
            continue
        _entries = _dat.get('entries') or []
        _filtered = [
            _e for _e in _entries
            if _path_lookup_key(_e.get('path')) not in _drop_keys
        ]
        if len(_filtered) != len(_entries):
            _dat['entries'] = _filtered
            _dat['fileCount'] = len(_filtered)


def flush_unknown_cache_root(root_path, p4_user=None, p4_client=None):
    """Drop cached unknown-files payload for one project root (user/client)."""
    _root = _normalize_disk_path(root_path)
    if not _root:
        return False
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return False
    _store = _unknown_cache_store()
    _key = _unknown_cache_key(_user, _client, _root)
    if _key in _store:
        del _store[_key]
        return True
    return False


def get_cached_unknown_files(root_path, p4_user=None, p4_client=None):
    """Return cached unknown-files payload for root, or None if not cached."""
    _root = _normalize_disk_path(root_path)
    if not _root:
        return None
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return None
    _cached = _unknown_cache_store().get(_unknown_cache_key(_user, _client, _root))
    if not _cached:
        return None
    return dict(_cached)


def collect_unknown_files(
        root_path,
        p4_user=None,
        p4_client=None,
        dir_mask=None,
        depot_paths=None,
        scope='project',
        progress_cb=None,
        cancel_cb=None,
        use_fstat_cache_depot_paths=True):
    """
    Find local in-client / not-on-depot files under root_path.

    depot_paths: normpaths already classified by recursive fstat (skip batch query).
    When use_fstat_cache_depot_paths is True, also skip paths already classified in
    the session fstat cache under root_path (union with depot_paths; protects Scene keys).
    progress_cb(processed, total, current_path) -> True to cancel.
    cancel_cb() -> True to cancel.

    Returns dict: ok, cancelled, root, scope, entries, fileCount, error.
    """
    _root = _normalize_disk_path(root_path)
    _result = {
        'ok': False,
        'cancelled': False,
        'root': _root,
        'scope': scope or 'project',
        'entries': [],
        'fileCount': 0,
        'error': None,
    }
    if not _root or not os.path.isdir(_root):
        _result['error'] = 'not a directory'
        return _result

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _result['error'] = _err
        return _result

    if not is_available(force=False, p4_user=_user, p4_client=_client):
        _result['error'] = 'p4 info failed'
        return _result

    _mask = [m for m in (dir_mask if dir_mask is not None else DEFAULT_P4_CACHE_DIR_MASK) if m]
    _depot_keys = set()
    _prefix_map = {}
    for _p in depot_paths or []:
        _norm = _disk_path_for_fstat_client_file(
            _p, p4_user=_user, p4_client=_client, prefix_map=_prefix_map)
        if not _norm:
            _norm = _normalize_disk_path(_p)
        _key = _path_lookup_key(_norm) if _norm else None
        if _key:
            _depot_keys.add(_key)

    _entries = []
    _cached_unknown_keys = set()
    if use_fstat_cache_depot_paths:
        _cache_depot, _cache_unknown = _fstat_cache_depot_skip_and_unknown(
            _root, _user, _client)
        _depot_keys.update(_cache_depot)
        for _entry in _cache_unknown:
            _entries.append(_entry)
            _key = _path_lookup_key(_entry.get('path'))
            if _key:
                _cached_unknown_keys.add(_key)
        if _cache_depot or _cache_unknown:
            log.info(
                'P4 unknown: fstat cache skip {0} depot-classified, {1} cached unknown'.format(
                    len(_cache_depot), len(_cache_unknown)))

    _disk_files = _collect_disk_files(_root, _mask)
    _candidates = []
    for _path in _disk_files:
        _key = _path_lookup_key(_path)
        if not _key or _key in _depot_keys or _key in _cached_unknown_keys:
            continue
        _candidates.append(_path)

    _total = len(_candidates)
    _processed = 0

    if _depot_keys or _cached_unknown_keys:
        log.info(
            'P4 unknown: {0} candidate(s) need fstat ({1} on disk)'.format(
                _total, len(_disk_files)))

    if progress_cb:
        progress_cb(0, _total, _root)

    for _i in range(0, _total, FSTAT_QUERY_CHUNK):
        if cancel_cb and cancel_cb():
            _result['cancelled'] = True
            break
        _chunk = _candidates[_i:_i + FSTAT_QUERY_CHUNK]
        if not _chunk:
            continue

        def _chunk_progress_cb(step, total, status):
            if cancel_cb and cancel_cb():
                return True
            if progress_cb:
                _idx = min(_processed + step, _total)
                _cur = _chunk[min(step - 1, len(_chunk) - 1)] if step > 0 and _chunk else _root
                return progress_cb(_idx, _total, _cur)
            return False

        _status = query_files_status(
            _chunk,
            p4_user=_user,
            p4_client=_client,
            force=False,
            progress_cb=_chunk_progress_cb if progress_cb else None,
        )
        if cancel_cb and cancel_cb():
            _result['cancelled'] = True
            break

        for _path in _chunk:
            _norm = _normalize_disk_path(_path)
            _dat = _status.get(_norm)
            if not _dat or not _is_unknown_file(_dat):
                continue
            _entries.append({'path': _norm, 'dat': dict(_dat)})

        _processed = min(_i + len(_chunk), _total)
        if progress_cb:
            _last = _chunk[-1]
            if progress_cb(_processed, _total, _last):
                _result['cancelled'] = True
                break

    _entries.sort(key=lambda _e: (_e.get('path') or '').lower())
    _payload = {
        'root': _root,
        'scope': scope or 'project',
        'entries': _entries,
        'fileCount': len(_entries),
    }
    if not _result['cancelled']:
        _unknown_cache_store()[_unknown_cache_key(_user, _client, _root)] = dict(_payload)
        _result['ok'] = True

    _result['entries'] = _entries
    _result['fileCount'] = len(_entries)
    return _result


def warm_fstat_cache_tree(
        root_path,
        p4_user=None,
        p4_client=None,
        dir_mask=None,
        progress_cb=None,
        cancel_cb=None):
    """
    Warm session fstat cache under root_path using one recursive p4 fstat (path/...).

    progress_cb(files_cached, files_total, current_path, dirs_done=0, dir_total=0, current_dir=None)
        files_total=0 while streaming (bar uses headroom max). files_total>0 on final tick only.
        Return True to cancel.
    cancel_cb() -> True to cancel.

    Returns dict: ok, cancelled, path, fileCount, fileTotal, dirTotal, unknownCount, error.
    """
    _fetch = fetch_fstat_tree_records(
        root_path,
        p4_user=p4_user,
        p4_client=p4_client,
        dir_mask=dir_mask,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
    )
    _result = {
        'ok': False,
        'cancelled': _fetch.get('cancelled', False),
        'path': _fetch.get('path'),
        'fileCount': 0,
        'fileTotal': 0,
        'dirTotal': _fetch.get('dirTotal', 0),
        'unknownCount': 0,
        'error': _fetch.get('error'),
    }
    if _fetch.get('error') or _fetch.get('cancelled'):
        _result['fileCount'] = _fetch.get('fileCount', 0)
        _result['fileTotal'] = _fetch.get('fileCount', 0)
        _result['ok'] = False
        return _result

    _records = _fetch.get('records') or []
    _store_res = store_fstat_cache_records(_records, p4_user=p4_user, p4_client=p4_client)
    if not _store_res.get('ok'):
        _result['error'] = _store_res.get('error') or 'cache store failed'
        return _result

    _count = _store_res.get('fileCount', 0)
    _result['fileCount'] = _count
    _result['fileTotal'] = _count
    _result['ok'] = True
    if progress_cb and _records:
        _last = _records[-1]['norm']
        _parent = os.path.normpath(os.path.dirname(_last))
        if progress_cb(
                _count, max(_count, 1), _last,
                _fetch.get('dirTotal', 0), _fetch.get('dirTotal', 0),
                _parent):
            _result['cancelled'] = True
            _result['ok'] = False
            return _result

    _depot_paths = {(_rec.get('norm') or '') for _rec in _records if _rec.get('norm')}

    def _unknown_progress_cb(processed, total, current_path):
        if cancel_cb and cancel_cb():
            return True
        if not progress_cb:
            return False
        return progress_cb(processed, max(total, 1), current_path)

    _unknown = collect_unknown_files(
        root_path,
        p4_user=p4_user,
        p4_client=p4_client,
        dir_mask=dir_mask,
        depot_paths=_depot_paths,
        scope='project',
        progress_cb=_unknown_progress_cb if progress_cb else None,
        cancel_cb=cancel_cb,
    )
    _result['unknownCount'] = _unknown.get('fileCount', 0)
    if _unknown.get('cancelled'):
        _result['cancelled'] = True
        _result['ok'] = False
    return _result


def is_under_client(disk_path, p4_user=None, p4_client=None, force=False):
    """True when disk_path is mapped in the current p4 client workspace."""
    _dat = query_file_status(disk_path, p4_user=p4_user, p4_client=p4_client, force=force)
    if _dat.get('error') and not _dat.get('notInClient'):
        return False
    return bool(_dat.get('inClient'))


def query_path(disk_path, p4_user=None, p4_client=None, force=False):
    """Alias for query_file_status — workspace check + file status in one call."""
    return query_file_status(disk_path, p4_user=p4_user, p4_client=p4_client, force=force)


def query_path_report(disk_path, p4_user=None, p4_client=None, force=True):
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
        if _dat.get('otherOpenActions'):
            log.info('otherAction: {0}'.format(_dat.get('otherOpenActions')))
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


def _pending_change_description_map(pending_dat):
    _map = {}
    if not pending_dat or pending_dat.get('error'):
        return _map
    for _ch in pending_dat.get('changes') or []:
        _cl = _ch.get('change')
        if _cl is not None:
            _map[str(_cl)] = (_ch.get('description') or '').strip()
    return _map


def iter_opened_changelist_groups(opened_dat, pending_dat=None):
    """
    Display-order changelist groups from query_opened dict.

    Returns list of dicts: change, label, description, entries.
    """
    if not opened_dat or opened_dat.get('error'):
        return []

    _desc_map = _pending_change_description_map(pending_dat)
    _groups = []
    _default = opened_dat.get('default') or []
    if _default:
        _entries = [dict(_rec) for _rec in _default]
        _groups.append({
            'change': 'default',
            'label': 'Default ({0})'.format(len(_entries)),
            'description': '',
            'entries': _entries,
        })

    for _cl in sorted((opened_dat.get('changes') or {}).keys(), key=_change_sort_key):
        _entries = [dict(_rec) for _rec in opened_dat['changes'][_cl]]
        _desc = _desc_map.get(str(_cl), '')
        _groups.append({
            'change': _cl,
            'label': 'Change {0} ({1})'.format(_cl, len(_entries)),
            'description': _desc,
            'entries': _entries,
        })
    return _groups


def iter_shelved_changelist_groups(shelved_dat):
    """
    Display-order shelved changelist groups from query_shelved dict.

    Returns list of dicts: change, label, description, entries.
    """
    if not shelved_dat or shelved_dat.get('error'):
        return []

    _groups = []
    for _cl in sorted((shelved_dat.get('changes') or {}).keys(), key=_change_sort_key):
        _block = shelved_dat['changes'][_cl]
        _entries = [dict(_rec) for _rec in (_block.get('entries') or [])]
        _desc = (_block.get('description') or '').strip()
        _desc_preview = _desc.splitlines()[0].strip()
        if len(_desc_preview) > 48:
            _desc_preview = _desc_preview[:45] + '...'
        _label = 'Change {0} ({1})'.format(_cl, len(_entries))
        if _desc_preview:
            _label = '{0} — {1}'.format(_label, _desc_preview)
        _groups.append({
            'change': _cl,
            'label': _label,
            'description': _desc,
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
        invalidate_fstat_paths([_path], p4_user=_user, p4_client=_client)
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
        invalidate_fstat_paths([_path], p4_user=_user, p4_client=_client)
        invalidate_unknown_paths([_path], p4_user=_user, p4_client=_client)
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


def resolve_revert_path(entry, p4_user=None, p4_client=None, force=False):
    """
    Resolve path for p4 revert from an opened-file record.

    Prefer client-root disk path (Scene browser style) via p4 where on depotFile,
    then clientFile — not raw UNC clientFile from p4 opened.
    """
    if not entry:
        return None
    _candidates = []
    _depot = entry.get('depotFile')
    if _depot:
        _candidates.append(str(_depot).split('#')[0].strip())
    _cf = entry.get('clientFile')
    if _cf:
        _candidates.append(str(_cf).strip())
    for _raw in _candidates:
        _disk = resolve_client_disk_path(
            _raw, p4_user=p4_user, p4_client=p4_client, force=force)
        if _disk:
            return _disk
    return _candidates[0] if _candidates else None


def revert_opened_entry(entry, p4_user=None, p4_client=None, force=False, keep_workspace=False):
    """p4 revert — discard local open using depot-aware path from an opened record."""
    _path = resolve_revert_path(entry, p4_user=p4_user, p4_client=p4_client, force=force)
    if not _path:
        return {
            'ok': False,
            'action': 'revert',
            'path': None,
            'stderr': 'opened entry missing depot and client path',
            'lines': [],
        }
    return revert(_path, p4_user=p4_user, p4_client=p4_client, force=force, keep_workspace=keep_workspace)


def revert(disk_path, p4_user=None, p4_client=None, force=False, keep_workspace=False):
    """p4 revert — discard local open on file."""
    _path = resolve_client_disk_path(
        disk_path, p4_user=p4_user, p4_client=p4_client, force=force)
    if not _path:
        _path = _normalize_disk_path(disk_path)
    if not _path:
        return {'ok': False, 'action': 'revert', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'revert', 'path': _path, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'revert', 'path': _path, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['revert']
    if keep_workspace:
        _args.append('-k')
    _args.append(_path)
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        invalidate_fstat_paths([_path], p4_user=_user, p4_client=_client)
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
        _fstat_cache_store().clear()
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
        invalidate_fstat_paths([_path], p4_user=_user, p4_client=_client)

    _out = _write_result('sync', _path, _res)
    _out['path'] = _path
    return _out


def sync_directory(
        dir_path,
        force=False,
        p4_user=None,
        p4_client=None,
        progress_cb=None,
        cancel_cb=None,
        progress_every=25,
        fstat_cache_flush='directory'):
    """
    p4 sync — update a directory and all files beneath to head revision.

    fstat_cache_flush: 'directory' (default), 'all' (O(1) full cache clear), or 'none'.
    progress_every: throttle progress_cb to every N sync output lines.
    """
    _dir = _normalize_disk_path(dir_path)
    if not _dir:
        return {'ok': False, 'action': 'sync', 'path': disk_path, 'stderr': 'path is empty', 'lines': []}

    if not os.path.isdir(_dir):
        return {'ok': False, 'action': 'sync', 'path': _dir, 'stderr': 'not a directory', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'sync', 'path': _dir, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'sync', 'path': _dir, 'stderr': 'p4 info failed', 'lines': []}

    _target = _sync_target_head(_dir)
    if not _target:
        return {'ok': False, 'action': 'sync', 'path': _dir, 'stderr': 'path is empty', 'lines': []}

    _res = _p4run_sync(
        _target,
        force=force,
        p4_user=_user,
        p4_client=_client,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
        progress_every=progress_every,
    )

    if _res.get('ok') and fstat_cache_flush != 'none':
        if fstat_cache_flush == 'all':
            flush_fstat_cache(p4_user=_user, p4_client=_client)
        else:
            invalidate_fstat_directory(_dir, p4_user=_user, p4_client=_client)

    _out = _write_result('sync', _dir, _res)
    _out['path'] = _dir
    _out['target'] = _target
    _out['cancelled'] = bool(_res.get('cancelled'))
    _out['fileCount'] = len(_res.get('lines') or [])
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
        _fstat_cache_store().clear()

    return {
        'ok': bool(_res.get('ok')),
        'action': 'sync',
        'target': _target,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def submit_change(change, description=None, p4_user=None, p4_client=None, force=False,
                  progress_cb=None):
    """p4 submit — submit pending changelist (or default when change is 'default')."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    _desc = (description or '').strip()
    _cl_label = 'default changelist' if _change_str in ('default', '') else 'changelist {0}'.format(change)
    if _submit_progress_tick(progress_cb, 1, 1, 'P4 Submit | submitting {0}'.format(_cl_label)):
        return _submit_progress_cancelled(change)

    if _change_str in ('default', ''):
        _args = ['submit']
        if _desc:
            _args.extend(['-d', _desc])
        _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    elif _desc:
        _spec, _spec_err = _fetch_change_spec(change, p4_user=_user, p4_client=_client)
        if _spec_err or not _spec:
            return {
                'ok': False, 'action': 'submit', 'change': change,
                'stderr': _spec_err or 'p4 change -o failed', 'lines': [],
            }
        _depot_keys, _depot_err = _depot_keys_for_submit_from_spec(_spec)
        if _depot_err:
            return {
                'ok': False, 'action': 'submit', 'change': change,
                'stderr': _depot_err, 'lines': [],
            }
        _submit_spec = _build_changelist_form_spec(_spec, _depot_keys, _desc)
        _res = _p4run_input(
            'submit', '-i', input_text=_submit_spec,
            p4_user=_user, p4_client=_client, ztag=False,
        )
    else:
        _args = ['submit', '-c', str(change)]
        _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)

    if _res.get('ok'):
        _fstat_cache_store().clear()

    return {
        'ok': bool(_res.get('ok')),
        'action': 'submit',
        'change': change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def _depot_keys_for_submit_from_spec(spec_text):
    """Collect all depot keys listed in a change spec Files section."""
    _keys = set()
    _section = None
    for _line in (spec_text or '').splitlines():
        if _line.startswith('Files:'):
            _section = 'files'
            continue
        if _section == 'files':
            _stripped = _line.strip()
            if _stripped.startswith('//'):
                _key = _depot_path_key(_stripped.split()[0])
                if _key:
                    _keys.add(_key)
                continue
            if not _stripped:
                continue
            _section = None
    if not _keys:
        return None, 'changelist has no files'
    return _keys, None


def _client_paths_from_opened_entries(entries):
    """Prefer clientFile for p4 reopen/submit CLI (depot fallback)."""
    _paths = []
    for _entry in entries or []:
        _path = _entry.get('clientFile') or _entry.get('depotFile')
        if _path:
            _paths.append(str(_path).strip())
    return _paths


def _submit_progress_cancelled(change, paths=None):
    return {
        'ok': False,
        'action': 'submit',
        'change': change,
        'paths': paths or [],
        'cancelled': True,
        'stderr': 'cancelled',
        'lines': [],
    }


def _submit_progress_tick(progress_cb, step, total, status):
    if progress_cb and progress_cb(int(step), int(total), status):
        return True
    return False


def _submit_status_basename(path):
    _name = os.path.basename(str(path or ''))
    if len(_name) <= 48:
        return _name
    return '...{0}'.format(_name[-45:])


def reopen_paths(paths, change, p4_user=None, p4_client=None, force=False):
    """p4 reopen -c changelist — move opened files to another pending changelist."""
    _paths = []
    for _raw in paths or []:
        _path = str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {'ok': False, 'action': 'reopen', 'change': change, 'stderr': 'no paths', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'reopen', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'reopen', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['reopen', '-c', _change_spec_arg(change)] + _paths
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        invalidate_fstat_paths(_paths, p4_user=_user, p4_client=_client)

    return {
        'ok': bool(_res.get('ok')),
        'action': 'reopen',
        'change': change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def _submit_default_partial(client_paths, description, p4_user=None, p4_client=None, force=False,
                            progress_cb=None):
    """
    Submit a subset of files from the default changelist.

    P4 rejects submit -i with Change: default. Single file: p4 submit -d DESC path.
    Multiple files: create numbered CL, reopen files, p4 submit -c CL.
    """
    _paths = [str(_p).strip() for _p in (client_paths or []) if str(_p).strip()]
    if not _paths:
        return {'ok': False, 'action': 'submit', 'change': 'default', 'stderr': 'no paths', 'lines': []}

    _desc = (description or '').strip()
    if not _desc:
        return {
            'ok': False, 'action': 'submit', 'change': 'default',
            'stderr': 'submit description is required', 'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit', 'change': 'default', 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit', 'change': 'default', 'stderr': 'p4 info failed', 'lines': []}

    if len(_paths) == 1:
        if _submit_progress_tick(
                progress_cb, 1, 1,
                'P4 Submit | {0}'.format(_submit_status_basename(_paths[0]))):
            return _submit_progress_cancelled('default', _paths)
        _res = _p4run(
            'submit', '-d', _desc, _paths[0],
            p4_user=_user, p4_client=_client, ztag=False,
        )
        if _res.get('ok'):
            invalidate_fstat_paths(_paths, p4_user=_user, p4_client=_client)
        return {
            'ok': bool(_res.get('ok')),
            'action': 'submit',
            'change': 'default',
            'paths': _paths,
            'stderr': _res.get('stderr') or '',
            'lines': _res.get('lines') or [],
        }

    if _submit_progress_tick(progress_cb, 1, 3, 'P4 Submit | creating changelist'):
        return _submit_progress_cancelled('default', _paths)

    _create = create_pending_change(_desc, p4_user=_user, p4_client=_client, force=force)
    if not _create.get('ok'):
        return {
            'ok': False, 'action': 'submit', 'change': 'default', 'paths': _paths,
            'stderr': _create.get('stderr') or 'create changelist failed',
            'lines': _create.get('lines') or [],
        }

    _new_cl = _create.get('change')
    if _submit_progress_tick(
            progress_cb, 2, 3,
            'P4 Submit | moving {0} file(s) to changelist {1}'.format(len(_paths), _new_cl)):
        return _submit_progress_cancelled(_new_cl, _paths)

    _reopen = reopen_paths(_paths, _new_cl, p4_user=_user, p4_client=_client, force=force)
    if not _reopen.get('ok'):
        return {
            'ok': False, 'action': 'submit', 'change': _new_cl, 'paths': _paths,
            'stderr': _reopen.get('stderr') or 'reopen to new changelist failed',
            'lines': _reopen.get('lines') or [],
        }

    if _submit_progress_tick(
            progress_cb, 3, 3,
            'P4 Submit | submitting changelist {0}'.format(_new_cl)):
        return _submit_progress_cancelled(_new_cl, _paths)

    _submit = submit_change(_new_cl, p4_user=_user, p4_client=_client, force=force)
    _submit['paths'] = _paths
    _submit['source_change'] = 'default'
    return _submit


def submit_paths(paths, change=None, description=None, p4_user=None, p4_client=None, force=False,
                 opened_entries=None, progress_cb=None):
    """p4 submit — submit specific opened files (optionally scoped to a changelist)."""
    _paths = []
    for _raw in paths or []:
        _path = _normalize_disk_path(_raw) or str(_raw).strip()
        if _path:
            _paths.append(_path)

    if not opened_entries and not _paths:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'no paths', 'lines': []}

    _desc = (description or '').strip()
    if not _desc:
        return {
            'ok': False, 'action': 'submit', 'change': change,
            'stderr': 'submit description is required', 'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        _client_paths = _client_paths_from_opened_entries(opened_entries) if opened_entries else _paths
        if not _client_paths and opened_entries:
            return {
                'ok': False, 'action': 'submit', 'change': change, 'paths': _paths,
                'stderr': 'opened entries missing client/depot paths', 'lines': [],
            }
        return _submit_default_partial(
            _client_paths, _desc, p4_user=_user, p4_client=_client, force=force,
            progress_cb=progress_cb)

    if opened_entries:
        _depot_lines, _depot_err = _depot_file_lines_for_opened_entries(
            opened_entries, p4_user=_user, p4_client=_client, force=force)
    else:
        _depot_lines, _depot_err = _depot_file_lines_for_paths(
            _paths, p4_user=_user, p4_client=_client, force=force)

    if _depot_err:
        return {
            'ok': False, 'action': 'submit', 'change': change, 'paths': _paths,
            'stderr': _depot_err, 'lines': [],
        }

    _file_count = len(_depot_lines)
    if _submit_progress_tick(
            progress_cb, 1, 1,
            'P4 Submit | {0} file(s) in changelist {1}'.format(_file_count, change)):
        return _submit_progress_cancelled(change, _paths)

    _spec, _spec_err = _fetch_change_spec(change, p4_user=_user, p4_client=_client)
    if _spec_err or not _spec:
        return {
            'ok': False, 'action': 'submit', 'change': change, 'paths': _paths,
            'stderr': _spec_err or 'p4 change -o failed', 'lines': [],
        }
    _depot_keys = set()
    for _line in _depot_lines:
        _key = _depot_path_key(_line.split('#')[0])
        if _key:
            _depot_keys.add(_key)
    _submit_spec = _build_changelist_form_spec(_spec, _depot_keys, _desc)
    _res = _p4run_input(
        'submit', '-i', input_text=_submit_spec,
        p4_user=_user, p4_client=_client, ztag=False,
    )

    if _res.get('ok'):
        invalidate_fstat_paths(_paths, p4_user=_user, p4_client=_client)

    return {
        'ok': bool(_res.get('ok')),
        'action': 'submit',
        'change': change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def _update_change_description(change, description, p4_user=None, p4_client=None):
    """Update Description on a pending numbered changelist via p4 change -i."""
    _desc = (description or '').strip()
    if not _desc:
        return {'ok': False, 'stderr': 'description is empty', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'stderr': _err, 'lines': []}

    _spec, _spec_err = _fetch_change_spec(change, p4_user=_user, p4_client=_client)
    if _spec_err or not _spec:
        return {'ok': False, 'stderr': _spec_err or 'p4 change -o failed', 'lines': []}

    _depot_keys, _depot_err = _depot_keys_for_submit_from_spec(_spec)
    if _depot_err:
        return {'ok': False, 'stderr': _depot_err, 'lines': []}

    _change_spec = _build_changelist_form_spec(_spec, _depot_keys, _desc)
    _res = _p4run_input(
        'change', '-i', input_text=_change_spec,
        p4_user=_user, p4_client=_client, ztag=False,
    )
    return {
        'ok': bool(_res.get('ok')),
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


_SHELVE_CHANGE_RE = re.compile(r'^Change\s+(\d+)\s+', re.IGNORECASE)
_CHANGE_CREATED_RE = re.compile(r'^Change\s+(\d+)\s+created', re.IGNORECASE)


def _parse_shelve_change_number(lines):
    """Parse new changelist number from p4 shelve stdout (default CL → Change: new flow)."""
    for _line in lines or []:
        _m = _SHELVE_CHANGE_RE.match(str(_line).strip())
        if _m:
            return _m.group(1)
    return None


def _parse_change_created_number(lines):
    """Parse changelist number from p4 change -i stdout (Change N created)."""
    for _line in lines or []:
        _m = _CHANGE_CREATED_RE.match(str(_line).strip())
        if _m:
            return int(_m.group(1))
    return _parse_shelve_change_number(lines)


def _change_key(change):
    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        return 'default'
    try:
        return int(_change_str)
    except (TypeError, ValueError):
        return _change_str


def _unshelve_target_args(target_change):
    """Build -c arg pair for p4 unshelve target changelist."""
    _key = _change_key(target_change)
    if _key == 'default':
        return ['-c', 'default']
    return ['-c', str(target_change)]


def create_pending_change(description, p4_user=None, p4_client=None, force=False):
    """Create empty pending changelist via p4 change -i (Change: new)."""
    _desc = (description or '').strip()
    if not _desc:
        return {
            'ok': False, 'action': 'create_change', 'change': None,
            'stderr': 'description is required', 'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'create_change', 'change': None, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {
            'ok': False, 'action': 'create_change', 'change': None,
            'stderr': 'p4 info failed', 'lines': [],
        }

    _change_spec = _build_new_change_form_spec(_client, [], _desc)
    _res = _p4run_input(
        'change', '-i', input_text=_change_spec,
        p4_user=_user, p4_client=_client, ztag=False,
    )
    if not _res.get('ok'):
        return {
            'ok': False, 'action': 'create_change', 'change': None,
            'stderr': _res.get('stderr') or 'p4 change -i failed', 'lines': _res.get('lines') or [],
        }

    _change = _parse_change_created_number(_res.get('lines'))
    if not _change:
        return {
            'ok': False, 'action': 'create_change', 'change': None,
            'stderr': 'could not parse created changelist number', 'lines': _res.get('lines') or [],
        }

    _fstat_cache_store().clear()
    return {
        'ok': True,
        'action': 'create_change',
        'change': _change,
        'stderr': '',
        'lines': _res.get('lines') or [],
    }


def unshelve_paths(paths, source_change, target_change, p4_user=None, p4_client=None, force=False):
    """p4 unshelve -s SOURCE -c TARGET — open shelved files in target changelist."""
    _paths = []
    for _raw in paths or []:
        _path = str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': 'no paths', 'lines': [],
        }

    if _change_key(source_change) == _change_key(target_change):
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': 'source and target changelist are the same',
            'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': _err, 'lines': [],
        }

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': 'p4 info failed', 'lines': [],
        }

    _args = ['unshelve', '-s', str(source_change)]
    _args.extend(_unshelve_target_args(target_change))
    if force:
        _args.append('-f')
    _args.extend(_paths)
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _fstat_cache_store().clear()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'unshelve',
        'source_change': source_change,
        'target_change': target_change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def unshelve_change(source_change, target_change, p4_user=None, p4_client=None, force=False):
    """p4 unshelve -s SOURCE -c TARGET — unshelve all files from shelved changelist."""
    if _change_key(source_change) == _change_key(target_change):
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change,
            'stderr': 'source and target changelist are the same', 'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': _err, 'lines': [],
        }

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {
            'ok': False, 'action': 'unshelve', 'source_change': source_change,
            'target_change': target_change, 'stderr': 'p4 info failed', 'lines': [],
        }

    _args = ['unshelve', '-s', str(source_change)]
    _args.extend(_unshelve_target_args(target_change))
    if force:
        _args.append('-f')
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _fstat_cache_store().clear()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'unshelve',
        'source_change': source_change,
        'target_change': target_change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def move_shelf_paths(paths, source_change, target_change, p4_user=None, p4_client=None, force=False):
    """Unshelve to target changelist, then delete shelf from source."""
    _paths = []
    for _raw in paths or []:
        _path = str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {
            'ok': False, 'action': 'move_shelf', 'source_change': source_change,
            'target_change': target_change, 'stderr': 'no paths', 'lines': [],
        }

    _uns = unshelve_paths(
        _paths, source_change, target_change,
        p4_user=p4_user, p4_client=p4_client, force=force,
    )
    if not _uns.get('ok'):
        _out = dict(_uns)
        _out['action'] = 'move_shelf'
        return _out

    _del = delete_shelf_paths(
        _paths, source_change, p4_user=p4_user, p4_client=p4_client, force=force,
    )
    if not _del.get('ok'):
        return {
            'ok': False,
            'action': 'move_shelf',
            'source_change': source_change,
            'target_change': target_change,
            'paths': _paths,
            'stderr': 'unshelve ok but delete shelf failed: {0}'.format(
                _del.get('stderr') or 'unknown'),
            'lines': _del.get('lines') or [],
            'unshelved': True,
        }

    return {
        'ok': True,
        'action': 'move_shelf',
        'source_change': source_change,
        'target_change': target_change,
        'paths': _paths,
        'stderr': '',
        'lines': (_uns.get('lines') or []) + (_del.get('lines') or []),
    }


def move_shelf_change(source_change, target_change, p4_user=None, p4_client=None, force=False):
    """Unshelve entire shelved changelist to target, then delete source shelf."""
    _uns = unshelve_change(
        source_change, target_change,
        p4_user=p4_user, p4_client=p4_client, force=force,
    )
    if not _uns.get('ok'):
        _out = dict(_uns)
        _out['action'] = 'move_shelf'
        return _out

    _del = delete_shelf_change(source_change, p4_user=p4_user, p4_client=p4_client, force=force)
    if not _del.get('ok'):
        return {
            'ok': False,
            'action': 'move_shelf',
            'source_change': source_change,
            'target_change': target_change,
            'stderr': 'unshelve ok but delete shelf failed: {0}'.format(
                _del.get('stderr') or 'unknown'),
            'lines': _del.get('lines') or [],
            'unshelved': True,
        }

    return {
        'ok': True,
        'action': 'move_shelf',
        'source_change': source_change,
        'target_change': target_change,
        'stderr': '',
        'lines': (_uns.get('lines') or []) + (_del.get('lines') or []),
    }


def _revert_paths_after_shelve(paths, p4_user=None, p4_client=None, force=False):
    """
    Revert workspace opens after shelve (P4V default).

    Shelved depot copies are kept; only local pending opens are cleared.
    Add files use p4 revert without -k (P4V removes from disk).
    """
    _paths = []
    for _raw in paths or []:
        _path = _normalize_disk_path(_raw) or str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {'ok': True, 'reverted': True, 'stderr': '', 'lines': []}

    _errors = []
    _reverted_any = False
    for _path in _paths:
        _stat = query_file_status(_path, p4_user=p4_user, p4_client=p4_client, force=True)
        if not _stat.get('checkedOut'):
            continue
        _rev = revert(
            _path, p4_user=p4_user, p4_client=p4_client, force=force, keep_workspace=False)
        if _rev.get('ok'):
            _reverted_any = True
        else:
            _errors.append('{0}: {1}'.format(_path, _rev.get('stderr') or 'revert failed'))

    _ok = not _errors
    if _errors:
        log.warning('P4 shelve revert-after: {0}'.format('; '.join(_errors)))
    return {
        'ok': _ok,
        'reverted': _ok and _reverted_any,
        'stderr': '; '.join(_errors),
        'lines': [],
    }


def shelve_change(change, description=None, p4_user=None, p4_client=None, force=False):
    """p4 shelve -Af — shelf entire pending changelist (files only, no stream spec)."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'shelve', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'shelve', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _change_str = str(change).lower() if change is not None else 'default'
    _desc = (description or '').strip()
    if not _desc:
        return {
            'ok': False, 'action': 'shelve', 'change': change,
            'stderr': 'shelve description is required', 'lines': [],
        }

    if _change_str in ('default', ''):
        _spec, _spec_err = _fetch_change_spec(change, p4_user=_user, p4_client=_client)
        if _spec_err or not _spec:
            return {
                'ok': False, 'action': 'shelve', 'change': change,
                'stderr': _spec_err or 'p4 change -o failed', 'lines': [],
            }
        _depot_lines = _depot_file_lines_from_spec(_spec)
        if not _depot_lines:
            return {
                'ok': False, 'action': 'shelve', 'change': change,
                'stderr': 'default changelist has no opened files', 'lines': [],
            }
        _shelve_spec = _build_new_change_form_spec(_client, _depot_lines, _desc)
        _res = _p4run_input(
            'shelve', '-Af', '-i', input_text=_shelve_spec,
            p4_user=_user, p4_client=_client, ztag=False,
        )
    else:
        _upd = _update_change_description(change, _desc, p4_user=_user, p4_client=_client)
        if not _upd.get('ok'):
            return {
                'ok': False, 'action': 'shelve', 'change': change,
                'stderr': _upd.get('stderr') or 'p4 change -i failed', 'lines': [],
            }
        _res = _p4run(
            'shelve', '-Af', '-c', str(change),
            p4_user=_user, p4_client=_client, ztag=False,
        )

    _revert = None
    if _res.get('ok'):
        _fstat_cache_store().clear()
        if _change_str in ('default', ''):
            _new_cl = _parse_shelve_change_number(_res.get('lines'))
            if _new_cl:
                _revert = revert_change(_new_cl, p4_user=_user, p4_client=_client, force=force)
            else:
                log.warning('P4 shelve: could not parse changelist number for revert-after-shelve')
                _revert = {
                    'ok': False, 'reverted': False,
                    'stderr': 'could not parse shelved changelist number', 'lines': [],
                }
        else:
            _revert = revert_change(change, p4_user=_user, p4_client=_client, force=force)
        if _revert and not _revert.get('ok'):
            log.warning(
                'P4 shelve revert-after failed: {0}'.format(_revert.get('stderr') or 'unknown'))

    return {
        'ok': bool(_res.get('ok')),
        'action': 'shelve',
        'change': change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
        'reverted': bool(_revert.get('ok')) if _revert else False,
        'revert_stderr': (_revert.get('stderr') or '') if _revert else '',
    }


def shelve_paths(paths, change=None, description=None, p4_user=None, p4_client=None, force=False,
                 opened_entries=None):
    """p4 shelve -Af — shelf specific opened files in a changelist."""
    _paths = []
    for _raw in paths or []:
        _path = _normalize_disk_path(_raw) or str(_raw).strip()
        if _path:
            _paths.append(_path)

    if opened_entries and not _paths:
        for _entry in opened_entries:
            _path = _entry.get('clientFile') or _entry.get('depotFile')
            if _path:
                _paths.append(_path)

    if not opened_entries and not _paths:
        return {'ok': False, 'action': 'shelve', 'change': change, 'stderr': 'no paths', 'lines': []}

    _desc = (description or '').strip()
    if not _desc:
        return {
            'ok': False, 'action': 'shelve', 'change': change,
            'stderr': 'shelve description is required', 'lines': [],
        }

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'shelve', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'shelve', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    if opened_entries:
        _depot_lines, _depot_err = _depot_file_lines_for_opened_entries(
            opened_entries, p4_user=_user, p4_client=_client, force=True)
    else:
        _depot_lines, _depot_err = _depot_file_lines_for_paths(
            _paths, p4_user=_user, p4_client=_client, force=True)

    _change_str = str(change).lower() if change is not None else 'default'
    if _change_str in ('default', ''):
        if _depot_err:
            return {
                'ok': False, 'action': 'shelve', 'change': change, 'paths': _paths,
                'stderr': _depot_err, 'lines': [],
            }
        _shelve_spec = _build_new_change_form_spec(_client, _depot_lines, _desc)
        _res = _p4run_input(
            'shelve', '-Af', '-i', input_text=_shelve_spec,
            p4_user=_user, p4_client=_client, ztag=False,
        )
    else:
        _upd = _update_change_description(change, _desc, p4_user=_user, p4_client=_client)
        if not _upd.get('ok'):
            return {
                'ok': False, 'action': 'shelve', 'change': change, 'paths': _paths,
                'stderr': _upd.get('stderr') or 'p4 change -i failed', 'lines': [],
            }
        _args = ['shelve', '-Af', '-c', str(change)] + _paths
        _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)

    _revert = None
    if _res.get('ok'):
        invalidate_fstat_paths(_paths, p4_user=_user, p4_client=_client)
        _revert = _revert_paths_after_shelve(
            _paths, p4_user=_user, p4_client=_client, force=force)
        if _revert and not _revert.get('ok'):
            log.warning(
                'P4 shelve revert-after failed: {0}'.format(_revert.get('stderr') or 'unknown'))

    return {
        'ok': bool(_res.get('ok')),
        'action': 'shelve',
        'change': change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
        'reverted': bool(_revert.get('ok')) if _revert else False,
        'revert_stderr': (_revert.get('stderr') or '') if _revert else '',
    }


def delete_shelf_change(change, p4_user=None, p4_client=None, force=False):
    """p4 shelve -d -Af — delete all shelved files from a changelist."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'delete_shelf', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'delete_shelf', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _res = _p4run(
        'shelve', '-d', '-Af', '-c', str(change),
        p4_user=_user, p4_client=_client, ztag=False,
    )
    if _res.get('ok'):
        _fstat_cache_store().clear()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'delete_shelf',
        'change': change,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def delete_shelf_paths(paths, change, p4_user=None, p4_client=None, force=False):
    """p4 shelve -d -Af — delete selected shelved files from a changelist."""
    _paths = []
    for _raw in paths or []:
        _path = str(_raw).strip()
        if _path:
            _paths.append(_path)
    if not _paths:
        return {'ok': False, 'action': 'delete_shelf', 'change': change, 'stderr': 'no paths', 'lines': []}

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'delete_shelf', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'delete_shelf', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['shelve', '-d', '-Af', '-c', str(change)] + _paths
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _fstat_cache_store().clear()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'delete_shelf',
        'change': change,
        'paths': _paths,
        'stderr': _res.get('stderr') or '',
        'lines': _res.get('lines') or [],
    }


def submit_shelved_change(change, description=None, p4_user=None, p4_client=None, force=False):
    """p4 submit -e — submit shelved files directly from a shelved changelist."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'ok': False, 'action': 'submit_shelved', 'change': change, 'stderr': _err, 'lines': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'ok': False, 'action': 'submit_shelved', 'change': change, 'stderr': 'p4 info failed', 'lines': []}

    _args = ['submit', '-e', '-c', str(change)]
    _desc = (description or '').strip()
    if _desc:
        _args.extend(['-d', _desc])
    _res = _p4run(*_args, p4_user=_user, p4_client=_client, ztag=False)
    if _res.get('ok'):
        _fstat_cache_store().clear()
    return {
        'ok': bool(_res.get('ok')),
        'action': 'submit_shelved',
        'change': change,
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
            log.debug('Using cached Perforce status')
            return _cached

    log.debug('Getting Perforce status...')
    _info = connection_info(force=force, p4_user=_user, p4_client=_client)

    _report = {
        'connected': bool(_info.get('connected')),
        'connection': _info,
        'p4User': _user,
        'p4Client': _client,
        'opened': None,
        'shelved': None,
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
    _report['shelved'] = query_shelved(p4_user=_user, p4_client=_client, force=force)
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

    _shelved = _dat.get('shelved') or {}
    if _shelved.get('error'):
        log.info(cgmGEN.logString_sub(_str_func, 'Shelved changelists'))
        log.info(_shelved['error'])
    else:
        _s_total = _shelved.get('total', 0)
        _s_cls = _shelved.get('rawCount', 0)
        log.info(cgmGEN.logString_sub(_str_func, 'Shelved changelists ({0} CL, {1} file(s))'.format(
            _s_cls, _s_total)))
        for _cl in sorted((_shelved.get('changes') or {}).keys(), key=lambda x: int(x) if str(x).isdigit() else x):
            _block = _shelved['changes'][_cl]
            _files = _block.get('entries') or []
            _desc = (_block.get('description') or '').splitlines()[0].strip()
            log.info('[change {0}] {1} shelved file(s){2}'.format(
                _cl, len(_files), ' — {0}'.format(_desc) if _desc else ''))
            for _rec in _files:
                _rev = _rec.get('rev')
                _rev_s = '#{0}'.format(_rev) if _rev is not None else ''
                log.info('  {0} {1}{2}'.format(_rec.get('action', '?'), _rec['depotFile'], _rev_s))

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
